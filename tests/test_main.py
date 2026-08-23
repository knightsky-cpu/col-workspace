import asyncio
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

import main
from artifact_feedback_service import (
    ArtifactFeedbackSchemaConflictError,
    ArtifactFeedbackStateError,
    ArtifactFeedbackTargetNotFoundError,
    ListArtifactFeedbackCommand,
)
from artifact_read_service import (
    ArtifactReadService,
    ArtifactReadStateError,
    GetBlueprintArtifactCommand,
    ListBlueprintArtifactsCommand,
)
from agent_col_turn_service import (
    AgentColTurnCommand,
    AgentColTurnResponderError,
    AgentColTurnResult,
    AgentColTurnRoutingError,
    AgentColTurnRoutingTimeoutError,
    AgentColTurnServiceError,
    AgentColTurnTimeoutError,
)
from chat_turns import (
    ChatTurnClaim,
    ChatTurnConflictError,
    ChatTurnIds,
    ChatTurnInProgressError,
    ChatTurnOwnershipError,
    ChatTurnReplay,
    ChatTurnRequest,
    ChatTurnStateError,
)
from database import (
    BlueprintArtifactCursorNotFoundError,
    BlueprintArtifactNotFoundError,
    BlueprintDocumentRecord,
    BlueprintFeedbackConflictError,
    BlueprintFeedbackCursorNotFoundError,
    BlueprintFeedbackStateError,
    MemoryEventCursorNotFoundError,
    MemoryProposalConflictError,
    MemoryProposalExpiredError,
    MemoryProposalNotFoundError,
    MemoryProposalOriginConflictError,
    MemoryProposalStateError,
    MemorySignalConflictError,
    MemorySignalNotFoundError,
)
from memory_proposals import ProposalTurnLease
from schemas import (
    AdaptationReceipt,
    AgentActionReceipt,
    ArtifactReference,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactFeedbackCounts,
    ArtifactFeedbackEvent,
    ArtifactFeedbackTarget,
    BlueprintArtifactDetailResponse,
    BlueprintArtifactFeedbackListResponse,
    BlueprintArtifactListResponse,
    BlueprintArtifactMetadata,
    ChatResponse,
    CitationReference,
    CollaborationProfile,
    MemoryDecisionRequest,
    MemoryEvent,
    MemoryProposal,
    MemoryProposalReceipt,
    SynthesisBlueprint,
)
from supervisor_runtime import (
    SupervisorRuntimeError,
    SupervisorTimeoutError,
    SupervisorTurnContext,
    SupervisorTurnResult,
)
from synthesis import SynthesisEngineError, SynthesisTimeoutError
from synthesis_service import (
    SynthesisCommand,
    SynthesisResult,
)
from trusted_memory_service import (
    DeleteMemorySignalCommand,
    InspectMemoryCommand,
    MemoryDecisionCommand,
    RevokeMemorySignalCommand,
    TrustedMemoryInspectionResult,
    TrustedMemoryMutationResult,
)
from vertex_config import VertexAISettings


VALID_BLUEPRINT_PAYLOAD = {
    "synthesized_conceptual_model": {
        "project_name": "Study Partner",
        "core_value_proposition": "Turns rubrics into executable plans.",
        "in_scope": ["Planning"],
        "out_of_scope": ["Automatic deployment"],
        "assumptions": ["The user reviews each milestone"],
    },
    "personalization_trace": {
        "adaptations": [
            {
                "profile_key": "experience_level",
                "architecture_change": "Adds smaller implementation steps.",
                "reason": "Supports an early-career developer.",
            }
        ]
    },
    "architectural_decisions": [
        {
            "component_name": "API",
            "proposed_solution": "FastAPI",
            "rationale": "Matches the existing asynchronous backend.",
            "alternatives": [
                {
                    "option_name": "Flask",
                    "tradeoff": "Simpler but synchronous by default.",
                    "reason_not_selected": (
                        "Would diverge from the backend."
                    ),
                }
            ],
        }
    ],
    "socratic_clarifying_questions": [
        {
            "question_text": "Which client should be supported first?",
            "why_this_matters": "It determines the first API contract.",
            "suggested_options": [
                {
                    "label": "Web",
                    "impact": "Reuses the existing FastAPI host.",
                },
                {
                    "label": "CLI",
                    "impact": "Optimizes for terminal workflows.",
                },
            ],
        }
    ],
    "step_by_step_execution_roadmap": [
        {
            "phase_name": "Phase 1: Contract",
            "objective": "Define the public request and response.",
            "expected_deliverable": "A tested Pydantic contract.",
            "micro_tasks": [
                {
                    "task_description": "Write the request model.",
                    "complexity_level": "Low",
                    "verification_steps": ["Run the schema tests."],
                }
            ],
        }
    ],
    "diagnostic_warnings": [],
}

MEMORY_NOW = datetime(2026, 8, 20, 23, 0, tzinfo=UTC)
DEFAULT_TURN_ID = "b" * 64


def make_chat_turn_claim(
    *,
    memory_decision: MemoryDecisionRequest | None = None,
    artifact_feedback_decision: ArtifactFeedbackDecisionRequest | None = None,
    owner_token: str = "owner-token-1",
    resumed: bool = False,
) -> ChatTurnClaim:
    return ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="New question",
            memory_decision=memory_decision,
            artifact_feedback_decision=artifact_feedback_decision,
        ),
        ids=ChatTurnIds(
            turn_id=DEFAULT_TURN_ID,
            user_message_id=f"turn--{DEFAULT_TURN_ID}--user",
            model_message_id=f"turn--{DEFAULT_TURN_ID}--model",
        ),
        owner_token=owner_token,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=120),
        resumed=resumed,
    )


def make_memory_proposal_receipt() -> MemoryProposalReceipt:
    return MemoryProposalReceipt(
        proposal_id="response_length--proposal-1",
        category="response_length",
        proposed_value="concise",
        expires_at=MEMORY_NOW + timedelta(hours=24),
    )


@dataclass
class FakeMemoryEngine:
    events: list[tuple[Any, ...]]
    collaboration_profile: CollaborationProfile = field(
        default_factory=CollaborationProfile
    )
    history: list[dict[str, object]] = field(
        default_factory=lambda: [
            {"role": "user", "text": "Earlier question"},
            {"role": "model", "text": "Earlier answer"},
        ]
    )
    fail_on: str | None = None
    chat_turn_result: ChatTurnClaim | ChatTurnReplay | None = None
    chat_turn_error: Exception | None = None
    renewed_claim: ChatTurnClaim | None = None
    renew_error: Exception | None = None
    released_claim: ChatTurnClaim | None = None
    release_error: Exception | None = None
    complete_error: Exception | None = None
    claim_calls: list[tuple[ChatTurnRequest, str, datetime]] = field(
        default_factory=list
    )
    renew_calls: list[tuple[ChatTurnClaim, datetime]] = field(
        default_factory=list
    )
    release_calls: list[tuple[ChatTurnClaim, datetime]] = field(
        default_factory=list
    )
    complete_calls: list[
        tuple[ChatTurnClaim, ChatResponse, datetime]
    ] = field(default_factory=list)
    decision_action_calls: list[
        tuple[ChatTurnClaim, AgentActionReceipt, datetime]
    ] = field(default_factory=list)
    closed: bool = False

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        if self.fail_on == "profile":
            raise main.MemoryEngineError("profile read failed")
        self.events.append(("collaboration_profile", user_id))
        return self.collaboration_profile

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
        *,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        if self.fail_on == "history":
            raise main.MemoryEngineError("history read failed")
        if exclude_message_id is None:
            self.events.append(("history", session_id, limit))
        else:
            self.events.append(
                (
                    "history",
                    session_id,
                    limit,
                    exclude_message_id,
                )
            )
        return self.history

    async def save_message(
        self, session_id: str, role: str, text: str
    ) -> str:
        if self.fail_on == f"save_{role}":
            raise main.MemoryEngineError(f"{role} save failed")
        self.events.append(("save", session_id, role, text))
        return f"{role}-message-1"

    async def claim_chat_turn(
        self,
        request: ChatTurnRequest,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ChatTurnClaim | ChatTurnReplay:
        self.claim_calls.append((request, idempotency_key, observed_at))
        self.events.append(("claim_chat_turn",))
        if self.chat_turn_error is not None:
            raise self.chat_turn_error
        if self.chat_turn_result is None:
            raise AssertionError("Missing fake chat-turn result.")
        return self.chat_turn_result

    async def renew_chat_turn_lease(
        self,
        claim: ChatTurnClaim,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        self.renew_calls.append((claim, observed_at))
        self.events.append(("renew_chat_turn_lease",))
        if self.renew_error is not None:
            raise self.renew_error
        return self.renewed_claim or claim

    async def release_chat_turn(
        self,
        claim: ChatTurnClaim,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        self.release_calls.append((claim, observed_at))
        self.events.append(("release_chat_turn",))
        if self.release_error is not None:
            raise self.release_error
        return self.released_claim or claim

    async def complete_chat_turn(
        self,
        claim: ChatTurnClaim,
        response: ChatResponse,
        *,
        observed_at: datetime,
    ) -> None:
        self.complete_calls.append((claim, response, observed_at))
        self.events.append(("complete_chat_turn",))
        if self.complete_error is not None:
            raise self.complete_error

    async def record_chat_turn_decision_action(
        self,
        claim: ChatTurnClaim,
        action: AgentActionReceipt,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        self.decision_action_calls.append((claim, action, observed_at))
        self.events.append(("record_chat_turn_decision_action",))
        return replace(
            claim,
            precompleted_actions=(*claim.precompleted_actions, action),
        )

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeAsyncGenAI:
    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeGenAIClient:
    aio: FakeAsyncGenAI
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeSourceExpertService:
    client: object


@dataclass
class FakeSynthesisApplicationService:
    events: list[tuple[Any, ...]]
    blueprint: SynthesisBlueprint
    error: Exception | None = None
    calls: list[SynthesisCommand] = field(default_factory=list)

    async def synthesize(
        self,
        command: SynthesisCommand,
    ) -> SynthesisResult:
        self.calls.append(command)
        self.events.append(("synthesis_service",))
        if self.error is not None:
            raise self.error
        return SynthesisResult(
            blueprint_id="blueprint-1",
            blueprint=self.blueprint,
        )


@dataclass
class FakeSupervisorRuntime:
    events: list[tuple[Any, ...]]
    response_text: str = "Generated answer"
    error: Exception | None = None
    calls: list[SupervisorTurnContext] = field(default_factory=list)
    turn_result: SupervisorTurnResult | None = None

    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult:
        self.calls.append(context)
        self.events.append(("supervisor",))
        if self.error is not None:
            raise self.error
        if self.turn_result is not None:
            return self.turn_result
        return SupervisorTurnResult(response=self.response_text)


@dataclass
class FakeAgentColTurnService:
    events: list[tuple[Any, ...]]
    response_text: str = "Generated answer"
    error: Exception | None = None
    calls: list[AgentColTurnCommand] = field(default_factory=list)
    turn_result: AgentColTurnResult | None = None

    async def run_turn(
        self,
        command: AgentColTurnCommand,
    ) -> AgentColTurnResult:
        self.calls.append(command)
        self.events.append(("turn_service",))
        if self.error is not None:
            raise self.error
        if self.turn_result is not None:
            return self.turn_result
        return AgentColTurnResult(response=self.response_text)


@dataclass
class FakeTrustedMemoryService:
    events: list[tuple[Any, ...]]
    result: TrustedMemoryInspectionResult
    error: Exception | None = None
    revoke_result: TrustedMemoryMutationResult | None = None
    delete_result: TrustedMemoryMutationResult | None = None
    decision_result: TrustedMemoryMutationResult | None = None
    calls: list[InspectMemoryCommand] = field(default_factory=list)
    revoke_calls: list[RevokeMemorySignalCommand] = field(
        default_factory=list
    )
    delete_calls: list[DeleteMemorySignalCommand] = field(
        default_factory=list
    )
    decision_calls: list[MemoryDecisionCommand] = field(
        default_factory=list
    )

    async def inspect_memory(
        self,
        command: InspectMemoryCommand,
    ) -> TrustedMemoryInspectionResult:
        self.calls.append(command)
        self.events.append(("memory_inspection",))
        if self.error is not None:
            raise self.error
        return self.result

    async def decide_memory_proposal(
        self,
        command: MemoryDecisionCommand,
    ) -> TrustedMemoryMutationResult:
        self.decision_calls.append(command)
        self.events.append(("memory_decision",))
        if self.error is not None:
            raise self.error
        if self.decision_result is None:
            raise AssertionError("Missing fake decision result.")
        return self.decision_result

    async def revoke_memory_signal(
        self,
        command: RevokeMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        self.revoke_calls.append(command)
        self.events.append(("memory_revoke",))
        if self.error is not None:
            raise self.error
        if self.revoke_result is None:
            raise AssertionError("Missing fake revocation result.")
        return self.revoke_result

    async def delete_memory_signal(
        self,
        command: DeleteMemorySignalCommand,
    ) -> TrustedMemoryMutationResult:
        self.delete_calls.append(command)
        self.events.append(("memory_delete",))
        if self.error is not None:
            raise self.error
        if self.delete_result is None:
            raise AssertionError("Missing fake deletion result.")
        return self.delete_result


@dataclass
class FakeArtifactReadService:
    events: list[tuple[Any, ...]]
    list_result: BlueprintArtifactListResponse
    detail_result: BlueprintArtifactDetailResponse
    list_error: Exception | None = None
    detail_error: Exception | None = None
    list_calls: list[ListBlueprintArtifactsCommand] = field(default_factory=list)
    detail_calls: list[GetBlueprintArtifactCommand] = field(default_factory=list)

    async def list_blueprints(
        self,
        command: ListBlueprintArtifactsCommand,
    ) -> BlueprintArtifactListResponse:
        self.list_calls.append(command)
        self.events.append(("artifact_list",))
        if self.list_error is not None:
            raise self.list_error
        return self.list_result

    async def get_blueprint(
        self,
        command: GetBlueprintArtifactCommand,
    ) -> BlueprintArtifactDetailResponse:
        self.detail_calls.append(command)
        self.events.append(("artifact_detail",))
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result


@dataclass
class FakeArtifactFeedbackService:
    result: BlueprintArtifactFeedbackListResponse
    error: Exception | None = None
    calls: list[ListArtifactFeedbackCommand] = field(default_factory=list)

    async def list_feedback(
        self,
        command: ListArtifactFeedbackCommand,
    ) -> BlueprintArtifactFeedbackListResponse:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class ServiceState:
    events: list[tuple[Any, ...]]
    database: FakeMemoryEngine
    genai_client: FakeGenAIClient
    synthesis_service: FakeSynthesisApplicationService
    source_service: FakeSourceExpertService
    research_service: object
    computation_service: object
    requirements_verification_service: object
    expert_executor: object
    supervisor: FakeSupervisorRuntime
    turn_service: FakeAgentColTurnService
    memory_service: FakeTrustedMemoryService
    artifact_service: FakeArtifactReadService
    artifact_executor: object
    artifact_feedback_service: FakeArtifactFeedbackService
    artifact_feedback_executor: object
    genai_client_kwargs: list[dict[str, object]]
    responder_vertex_settings: list[VertexAISettings]
    research_vertex_settings: list[VertexAISettings]
    computation_vertex_settings: list[VertexAISettings]
    requirements_verification_clients: list[object]
    responder_memory_services: list[object]
    expert_executor_dependencies: list[
        tuple[object, object, object | None, object | None]
    ]
    artifact_executor_dependencies: list[
        tuple[object, object, object]
    ]
    artifact_feedback_service_dependencies: list[tuple[object, object]]
    artifact_feedback_executor_dependencies: list[tuple[object, object]]
    turn_service_dependencies: list[
        tuple[object, object, object, object, object]
    ]


@pytest.fixture
def service_state(monkeypatch: pytest.MonkeyPatch) -> ServiceState:
    events: list[tuple[Any, ...]] = []
    database = FakeMemoryEngine(events)
    genai_client = FakeGenAIClient(FakeAsyncGenAI())
    blueprint = SynthesisBlueprint.model_validate(VALID_BLUEPRINT_PAYLOAD)
    synthesis_service = FakeSynthesisApplicationService(events, blueprint)
    source_service = FakeSourceExpertService(client=genai_client)
    research_service = object()
    computation_service = object()
    requirements_verification_service = object()
    expert_executor = object()
    responder_app = object()
    supervisor = FakeSupervisorRuntime(events)
    turn_service = FakeAgentColTurnService(events)
    pending_proposal = MemoryProposal(
        proposal_id="example_usage--proposal-1",
        category="example_usage",
        proposed_value="always_practical",
        expected_signal_id=None,
        status="pending",
        source_session_id="source-session",
        source_message_id="source-message",
        created_at=MEMORY_NOW,
        expires_at=MEMORY_NOW + timedelta(hours=24),
    )
    approved_event = MemoryEvent(
        event_id="response_length--signal-1--approved",
        event_type="approved",
        signal_id="response_length--signal-1",
        category="response_length",
        value="concise",
        source_type="explicit_user_feedback",
        source_session_id="source-session",
        source_message_id="source-message",
        confirmation_channel="memory_api",
        confirmation_session_id=None,
        confirmation_message_id=None,
        related_signal_id=None,
        memory_revision=1,
        created_at=MEMORY_NOW,
    )
    approved_profile = CollaborationProfile.model_validate(
        {
            "memory_revision": 2,
            "active_preferences": {
                "response_length": {
                    "signal_id": "response_length--proposal-1",
                    "category": "response_length",
                    "value": "concise",
                    "source_event_id": (
                        "response_length--proposal-1--approved"
                    ),
                    "approved_at": MEMORY_NOW,
                }
            },
        }
    )
    memory_service = FakeTrustedMemoryService(
        events=events,
        result=TrustedMemoryInspectionResult(
            profile=CollaborationProfile(memory_revision=1),
            unresolved_proposals=(pending_proposal,),
            events=(approved_event,),
            next_event_id="response_length--signal-1--approved",
        ),
        revoke_result=TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="revoke_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(memory_revision=2),
        ),
        delete_result=TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="delete_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(memory_revision=3),
        ),
        decision_result=TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="approve_memory_signal",
                status="completed",
            ),
            profile=approved_profile,
        ),
    )
    artifact_metadata = BlueprintArtifactMetadata(
        reference=ArtifactReference(
            artifact_type="synthesis_blueprint",
            project_id="project-1",
            artifact_id="blueprint-1",
            schema_version="2.0",
            display_label="Study Partner",
        ),
        created_at=MEMORY_NOW,
        originating_session_id="session-1",
        originating_turn_id=None,
        parent_artifact_id=None,
        feedback_counts=ArtifactFeedbackCounts(),
        adaptation_categories=[],
    )
    artifact_service = FakeArtifactReadService(
        events=events,
        list_result=BlueprintArtifactListResponse(
            artifacts=[artifact_metadata],
            next_before=None,
        ),
        detail_result=BlueprintArtifactDetailResponse(
            metadata=artifact_metadata,
            blueprint=blueprint,
            feedback_targets=[
                ArtifactFeedbackTarget(
                    target_id="target--0123456789abcdef01234567",
                    target_kind="whole_blueprint",
                    display_label="Study Partner",
                )
            ],
            adaptations=[],
            applied_feedback_ids=[],
        ),
    )
    artifact_executor = object()
    artifact_feedback_service = FakeArtifactFeedbackService(
        result=BlueprintArtifactFeedbackListResponse(
            artifact_id="blueprint-1",
            events=[],
            next_before=None,
        )
    )
    artifact_feedback_executor = object()
    genai_client_kwargs: list[dict[str, object]] = []
    responder_vertex_settings: list[VertexAISettings] = []
    research_vertex_settings: list[VertexAISettings] = []
    computation_vertex_settings: list[VertexAISettings] = []
    requirements_verification_clients: list[object] = []
    responder_memory_services: list[object] = []
    expert_executor_dependencies: list[
        tuple[object, object, object | None, object | None]
    ] = []
    artifact_executor_dependencies: list[
        tuple[object, object, object]
    ] = []
    artifact_feedback_service_dependencies: list[tuple[object, object]] = []
    artifact_feedback_executor_dependencies: list[tuple[object, object]] = []
    turn_service_dependencies: list[
        tuple[object, object, object, object, object]
    ] = []
    state = ServiceState(
        events=events,
        database=database,
        genai_client=genai_client,
        synthesis_service=synthesis_service,
        source_service=source_service,
        research_service=research_service,
        computation_service=computation_service,
        requirements_verification_service=(
            requirements_verification_service
        ),
        expert_executor=expert_executor,
        supervisor=supervisor,
        turn_service=turn_service,
        memory_service=memory_service,
        artifact_service=artifact_service,
        artifact_executor=artifact_executor,
        artifact_feedback_service=artifact_feedback_service,
        artifact_feedback_executor=artifact_feedback_executor,
        genai_client_kwargs=genai_client_kwargs,
        responder_vertex_settings=responder_vertex_settings,
        research_vertex_settings=research_vertex_settings,
        computation_vertex_settings=computation_vertex_settings,
        requirements_verification_clients=(
            requirements_verification_clients
        ),
        responder_memory_services=responder_memory_services,
        expert_executor_dependencies=expert_executor_dependencies,
        artifact_executor_dependencies=artifact_executor_dependencies,
        artifact_feedback_service_dependencies=(
            artifact_feedback_service_dependencies
        ),
        artifact_feedback_executor_dependencies=(
            artifact_feedback_executor_dependencies
        ),
        turn_service_dependencies=turn_service_dependencies,
    )

    def create_synthesis_service(**kwargs: object) -> object:
        assert kwargs == {
            "client": genai_client,
            "database": database,
        }
        return synthesis_service

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "True")
    monkeypatch.setattr(main, "MemoryEngine", lambda: database)

    def create_genai_client(**kwargs: object) -> FakeGenAIClient:
        genai_client_kwargs.append(kwargs)
        return genai_client

    monkeypatch.setattr(main.genai, "Client", create_genai_client)
    monkeypatch.setattr(
        main,
        "SynthesisApplicationService",
        create_synthesis_service,
        raising=False,
    )

    def create_source_service(*, client: object) -> object:
        assert client is genai_client
        return source_service

    monkeypatch.setattr(
        main,
        "SourceExpertService",
        create_source_service,
        raising=False,
    )

    def create_research_service(
        vertex_settings: VertexAISettings,
    ) -> object:
        research_vertex_settings.append(vertex_settings)
        return research_service

    monkeypatch.setattr(
        main,
        "ResearchExpertService",
        SimpleNamespace(from_vertex_settings=create_research_service),
        raising=False,
    )

    def create_computation_service(
        vertex_settings: VertexAISettings,
    ) -> object:
        computation_vertex_settings.append(vertex_settings)
        return computation_service

    monkeypatch.setattr(
        main,
        "ComputationalExpertService",
        SimpleNamespace(from_vertex_settings=create_computation_service),
        raising=False,
    )

    def create_requirements_verification_service(
        *,
        client: object,
    ) -> object:
        requirements_verification_clients.append(client)
        return requirements_verification_service

    monkeypatch.setattr(
        main,
        "RequirementsVerificationService",
        create_requirements_verification_service,
        raising=False,
    )

    def create_responder_app(
        *,
        vertex_settings: VertexAISettings,
        memory_service: object | None = None,
    ) -> object:
        responder_vertex_settings.append(vertex_settings)
        responder_memory_services.append(memory_service)
        return responder_app

    monkeypatch.setattr(
        main,
        "create_responder_app",
        create_responder_app,
        raising=False,
    )

    def create_expert_executor(
        *,
        source_service: object,
        research_service: object,
        computation_service: object | None = None,
        requirements_verification_service: object | None = None,
    ) -> object:
        expert_executor_dependencies.append(
            (
                source_service,
                research_service,
                computation_service,
                requirements_verification_service,
            )
        )
        return expert_executor

    monkeypatch.setattr(
        main,
        "AgentColExpertExecutorV3",
        create_expert_executor,
        raising=False,
    )

    def create_turn_service(
        *,
        routing_client: object,
        expert_executor: object,
        responder_runtime: object,
        artifact_executor: object,
        artifact_feedback_executor: object,
    ) -> object:
        turn_service_dependencies.append(
            (
                routing_client,
                expert_executor,
                responder_runtime,
                artifact_executor,
                artifact_feedback_executor,
            )
        )
        return turn_service

    monkeypatch.setattr(
        main,
        "AgentColTurnService",
        create_turn_service,
        raising=False,
    )

    monkeypatch.setattr(
        main,
        "SupervisorRuntime",
        SimpleNamespace(
            from_app=lambda app: supervisor
        ),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "TrustedMemoryService",
        lambda *, database: (
            memory_service
            if database is state.database
            else pytest.fail("Unexpected memory service database.")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "ArtifactReadService",
        lambda *, database: (
            artifact_service
            if database is state.database
            else pytest.fail("Unexpected artifact service database.")
        ),
        raising=False,
    )

    def create_artifact_executor(
        *,
        synthesis_service: object,
        artifact_ledger: object,
        artifact_reader: object,
    ) -> object:
        artifact_executor_dependencies.append(
            (synthesis_service, artifact_ledger, artifact_reader)
        )
        return artifact_executor

    monkeypatch.setattr(
        main,
        "AgentColArtifactExecutor",
        create_artifact_executor,
        raising=False,
    )

    def create_artifact_feedback_service(
        *,
        artifact_reader: object,
        feedback_repository: object,
    ) -> object:
        artifact_feedback_service_dependencies.append(
            (artifact_reader, feedback_repository)
        )
        return artifact_feedback_service

    monkeypatch.setattr(
        main,
        "ArtifactFeedbackService",
        create_artifact_feedback_service,
        raising=False,
    )

    def create_artifact_feedback_executor(
        *,
        feedback_resolver: object,
        feedback_ledger: object,
    ) -> object:
        artifact_feedback_executor_dependencies.append(
            (feedback_resolver, feedback_ledger)
        )
        return artifact_feedback_executor

    monkeypatch.setattr(
        main,
        "AgentColArtifactFeedbackExecutor",
        create_artifact_feedback_executor,
        raising=False,
    )
    return state


@pytest_asyncio.fixture
async def client(service_state: ServiceState):
    async with main.lifespan(main.app):
        transport = httpx.ASGITransport(
            app=main.app,
            raise_app_exceptions=False,
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            yield test_client


@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "online"}


@pytest.mark.asyncio
async def test_memory_inspection_returns_typed_service_result(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/users/user-1/memory",
        params={
            "after_event_id": "response_length--cursor--approved",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile": {
            "memory_schema_version": "1.0",
            "memory_revision": 1,
            "identity_context": {},
            "active_preferences": {},
        },
        "unresolved_proposals": [
            {
                "proposal_id": "example_usage--proposal-1",
                "category": "example_usage",
                "proposed_value": "always_practical",
                "expected_signal_id": None,
                "policy_version": "1.0",
                "status": "pending",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "created_at": "2026-08-20T23:00:00Z",
                "expires_at": "2026-08-21T23:00:00Z",
            }
        ],
        "events": [
            {
                "event_id": "response_length--signal-1--approved",
                "event_type": "approved",
                "signal_id": "response_length--signal-1",
                "category": "response_length",
                "value": "concise",
                "policy_version": "1.0",
                "source_type": "explicit_user_feedback",
                "source_session_id": "source-session",
                "source_message_id": "source-message",
                "confirmation_channel": "memory_api",
                "confirmation_session_id": None,
                "confirmation_message_id": None,
                "related_signal_id": None,
                "memory_revision": 1,
                "created_at": "2026-08-20T23:00:00Z",
            }
        ],
        "next_event_id": "response_length--signal-1--approved",
    }
    assert service_state.memory_service.calls == [
        InspectMemoryCommand(
            user_id="user-1",
            after_event_id="response_length--cursor--approved",
        )
    ]


@pytest.mark.asyncio
async def test_memory_inspection_maps_missing_user_cursor_to_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemoryEventCursorNotFoundError(
        "private cursor detail"
    )

    response = await client.get(
        "/api/users/user-1/memory",
        params={"after_event_id": "response_length--missing--approved"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Memory event cursor was not found."
    }


@pytest.mark.asyncio
async def test_memory_inspection_translates_database_failure_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "private-user private-memory-value"
    service_state.memory_service.error = main.MemoryEngineError(
        private_detail
    )

    response = await client.get("/api/users/private-user/memory")

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert "private-user" not in caplog.text
    assert "private-memory-value" not in caplog.text


@pytest.mark.parametrize(
    ("path", "params"),
    (
        (f"/api/users/{'u' * 129}/memory", None),
        (
            "/api/users/user-1/memory",
            {"after_event_id": "invalid/cursor"},
        ),
        (
            "/api/users/user-1/memory",
            {"after_event_id": "   "},
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_inspection_rejects_invalid_identifiers_before_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    path: str,
    params: dict[str, str] | None,
) -> None:
    response = await client.get(path, params=params)

    assert response.status_code == 422
    assert service_state.memory_service.calls == []


@pytest.mark.asyncio
async def test_revoke_memory_signal_returns_mutation_receipt(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--signal-1/revoke"
    )

    assert response.status_code == 200
    assert response.json() == {
        "action": {
            "action_name": "revoke_memory_signal",
            "status": "completed",
        },
        "profile": {
            "memory_schema_version": "1.0",
            "memory_revision": 2,
            "identity_context": {},
            "active_preferences": {},
        },
    }
    assert service_state.memory_service.revoke_calls == [
        RevokeMemorySignalCommand(
            user_id="user-1",
            signal_id="response_length--signal-1",
        )
    ]


@pytest.mark.asyncio
async def test_delete_memory_signal_returns_no_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.delete(
        "/api/users/user-1/memory/signals/response_length--signal-1"
    )

    assert response.status_code == 204
    assert response.content == b""
    assert service_state.memory_service.delete_calls == [
        DeleteMemorySignalCommand(
            user_id="user-1",
            signal_id="response_length--signal-1",
        )
    ]


@pytest.mark.asyncio
async def test_revoke_memory_signal_maps_unknown_signal_to_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemorySignalNotFoundError(
        "private signal detail"
    )

    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--missing/revoke"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Memory signal was not found."}


@pytest.mark.asyncio
async def test_revoke_memory_signal_maps_state_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.error = MemorySignalConflictError(
        "private conflict detail"
    )

    response = await client.post(
        "/api/users/user-1/memory/signals/"
        "response_length--signal-1/revoke"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Memory signal state conflicts with this request."
    }


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            f"/api/users/{'u' * 129}/memory/signals/"
            "response_length--signal-1/revoke",
        ),
        (
            "POST",
            "/api/users/user-1/memory/signals/"
            f"response_length--{'s' * 129}/revoke",
        ),
        (
            "DELETE",
            f"/api/users/{'u' * 129}/memory/signals/"
            "response_length--signal-1",
        ),
        (
            "DELETE",
            "/api/users/user-1/memory/signals/"
            f"response_length--{'s' * 129}",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_reject_invalid_identifiers_before_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    method: str,
    path: str,
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 422
    assert service_state.memory_service.revoke_calls == []
    assert service_state.memory_service.delete_calls == []


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            "/api/users/user-1/memory/signals/unknown--signal/revoke",
        ),
        (
            "DELETE",
            "/api/users/user-1/memory/signals/unknown--signal",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_map_invalid_governed_category(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    method: str,
    path: str,
) -> None:
    service_state.memory_service.error = ValueError(
        "private invalid category detail"
    )

    response = await client.request(method, path)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Memory signal identifier is invalid."
    }


@pytest.mark.parametrize(
    ("method", "path"),
    (
        (
            "POST",
            "/api/users/private-user/memory/signals/"
            "response_length--private-signal/revoke",
        ),
        (
            "DELETE",
            "/api/users/private-user/memory/signals/"
            "response_length--private-signal",
        ),
    ),
)
@pytest.mark.asyncio
async def test_memory_mutations_translate_database_failure_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
) -> None:
    service_state.memory_service.error = main.MemoryEngineError(
        "private-user private-signal private-memory-value"
    )

    response = await client.request(method, path)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert "private-user" not in caplog.text
    assert "private-signal" not in caplog.text
    assert "private-memory-value" not in caplog.text


@pytest.mark.asyncio
async def test_lifespan_does_not_expose_unrestricted_supervisor(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert not hasattr(main.app.state, "supervisor")


@pytest.mark.asyncio
async def test_lifespan_exposes_agent_col_turn_service(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert main.app.state.turn_service is service_state.turn_service


@pytest.mark.asyncio
async def test_lifespan_uses_explicit_vertex_clients_without_api_key(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        pass

    assert service_state.genai_client_kwargs == [
        {
            "enterprise": True,
            "project": "project-1",
            "location": "global",
        }
    ]
    assert service_state.responder_vertex_settings == [
        VertexAISettings(project="project-1", location="global")
    ]


@pytest.mark.asyncio
async def test_lifespan_injects_memory_only_into_responder_app(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert service_state.responder_memory_services == [
            service_state.memory_service
        ]


@pytest.mark.asyncio
async def test_lifespan_composes_deterministic_experts_and_turn_service(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert service_state.source_service.client is (
            service_state.genai_client
        )
        assert service_state.research_vertex_settings == [
            VertexAISettings(project="project-1", location="global")
        ]
        assert service_state.computation_vertex_settings == [
            VertexAISettings(project="project-1", location="global")
        ]
        assert service_state.requirements_verification_clients == [
            service_state.genai_client
        ]
        assert service_state.expert_executor_dependencies == [
            (
                service_state.source_service,
                service_state.research_service,
                service_state.computation_service,
                service_state.requirements_verification_service,
            )
        ]
        assert service_state.artifact_executor_dependencies == [
            (
                service_state.synthesis_service,
                service_state.database,
                service_state.artifact_service,
            )
        ]
        assert service_state.artifact_feedback_service_dependencies == [
            (
                service_state.artifact_service,
                service_state.database,
            )
        ]
        assert service_state.artifact_feedback_executor_dependencies == [
            (
                service_state.artifact_feedback_service,
                service_state.database,
            )
        ]
        assert service_state.turn_service_dependencies == [
            (
                service_state.genai_client,
                service_state.expert_executor,
                service_state.supervisor,
                service_state.artifact_executor,
                service_state.artifact_feedback_executor,
            )
        ]


@pytest.mark.asyncio
async def test_lifespan_exposes_synthesis_application_service(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert (
            main.app.state.synthesis_service
            is service_state.synthesis_service
        )


@pytest.mark.asyncio
async def test_lifespan_exposes_artifact_read_service(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert main.app.state.artifact_service is service_state.artifact_service


@pytest.mark.asyncio
async def test_lifespan_closes_resources_if_supervisor_construction_fails(
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_error = RuntimeError("supervisor construction failed")

    def fail_construction(
        app: object,
        *,
        delegation_registry: object | None = None,
    ) -> object:
        raise construction_error

    monkeypatch.setattr(
        main,
        "SupervisorRuntime",
        SimpleNamespace(from_app=fail_construction),
    )

    with pytest.raises(RuntimeError) as caught:
        async with main.lifespan(main.app):
            pass

    assert caught.value is construction_error
    assert service_state.database.closed
    assert service_state.genai_client.aio.closed
    assert service_state.genai_client.closed


@pytest.mark.asyncio
async def test_synthesize_returns_and_persists_blueprint(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "Build a study partner.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "blueprint_id": "blueprint-1",
        "blueprint": VALID_BLUEPRINT_PAYLOAD,
    }
    assert service_state.events == [("synthesis_service",)]
    assert service_state.synthesis_service.calls == [
        SynthesisCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_text="Build a study partner.",
        )
    ]


@pytest.mark.asyncio
async def test_list_blueprint_artifacts_returns_bounded_public_metadata(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/blueprints",
        params={"limit": 10, "before": "blueprint-cursor"},
    )

    assert response.status_code == 200
    assert response.json() == service_state.artifact_service.list_result.model_dump(
        mode="json"
    )
    assert service_state.artifact_service.list_calls == [
        ListBlueprintArtifactsCommand(
            project_id="project-1",
            limit=10,
            before="blueprint-cursor",
        )
    ]


@pytest.mark.asyncio
async def test_get_blueprint_artifact_returns_canonical_detail(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/blueprints/blueprint-1"
    )

    assert response.status_code == 200
    assert response.json() == service_state.artifact_service.detail_result.model_dump(
        mode="json"
    )
    assert service_state.artifact_service.detail_calls == [
        GetBlueprintArtifactCommand(
            project_id="project-1",
            blueprint_id="blueprint-1",
        )
    ]


@pytest.mark.asyncio
async def test_list_blueprint_feedback_returns_bounded_lifecycle(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    reference = ArtifactFeedbackReference(
        feedback_id="feedback--event-1",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=datetime(2026, 8, 23, 19, 0, tzinfo=UTC),
    )
    service_state.artifact_feedback_service.result = (
        BlueprintArtifactFeedbackListResponse(
            artifact_id="blueprint-1",
            events=[
                ArtifactFeedbackEvent(
                    reference=reference,
                    feedback_text="This boundary is correct.",
                    originating_session_id="session-1",
                    source_message_id="message-1",
                    originating_turn_id="turn-1",
                    status="active",
                )
            ],
            next_before="feedback--event-1",
        )
    )

    response = await client.get(
        "/api/projects/project-1/blueprints/blueprint-1/feedback",
        params={"limit": 10, "before": "feedback--cursor"},
    )

    assert response.status_code == 200
    assert response.json() == (
        service_state.artifact_feedback_service.result.model_dump(mode="json")
    )
    assert service_state.artifact_feedback_service.calls == [
        ListArtifactFeedbackCommand(
            project_id="project-1",
            artifact_id="blueprint-1",
            limit=10,
            before="feedback--cursor",
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            BlueprintFeedbackCursorNotFoundError("private cursor"),
            404,
            "Artifact feedback cursor was not found.",
        ),
        (
            ArtifactFeedbackStateError("private stored payload"),
            500,
            "Stored artifact feedback is invalid.",
        ),
    ),
)
async def test_list_blueprint_feedback_translates_safe_errors(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service_state.artifact_feedback_service.error = error

    response = await client.get(
        "/api/projects/project-1/blueprints/blueprint-1/feedback"
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_detail"),
    (
        (
            BlueprintArtifactCursorNotFoundError("missing"),
            "Blueprint artifact cursor was not found.",
        ),
        (
            ArtifactReadStateError("invalid"),
            "Stored blueprint artifact is invalid.",
        ),
    ),
)
async def test_list_blueprint_artifacts_translates_safe_errors(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_detail: str,
) -> None:
    service_state.artifact_service.list_error = error

    response = await client.get("/api/projects/project-1/blueprints")

    assert response.status_code == (
        404
        if isinstance(error, BlueprintArtifactCursorNotFoundError)
        else 500
    )
    assert response.json() == {"detail": expected_detail}


@pytest.mark.asyncio
async def test_get_blueprint_artifact_translates_missing_artifact(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.artifact_service.detail_error = BlueprintArtifactNotFoundError(
        "private artifact locator"
    )

    response = await client.get(
        "/api/projects/project-1/blueprints/missing-blueprint"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Blueprint artifact was not found."}


@pytest.mark.asyncio
async def test_get_blueprint_artifact_rejects_schema_v1_explicitly(
    client: httpx.AsyncClient,
) -> None:
    blueprint = deepcopy(VALID_BLUEPRINT_PAYLOAD)
    blueprint["architectural_decisions_and_feedback"] = blueprint.pop(
        "architectural_decisions"
    )
    record = BlueprintDocumentRecord(
        artifact_id="blueprint-v1",
        document={
            "created_at": MEMORY_NOW,
            "originating_session_id": "session-1",
            "user_id": "user-1",
            "model_name": "gemini-3.6-flash",
            "schema_version": "1.0",
            "blueprint": blueprint,
        },
    )

    class SchemaV1ArtifactDatabase:
        async def get_blueprint_document(
            self,
            project_id: str,
            blueprint_id: str,
        ) -> BlueprintDocumentRecord:
            assert project_id == "project-1"
            assert blueprint_id == "blueprint-v1"
            return record

    main.app.state.artifact_service = ArtifactReadService(
        database=SchemaV1ArtifactDatabase()
    )

    response = await client.get(
        "/api/projects/project-1/blueprints/blueprint-v1"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Blueprint artifact uses an unsupported schema version."
    }


@pytest.mark.asyncio
async def test_list_blueprint_artifacts_rejects_unbounded_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/blueprints",
        params={"limit": 51},
    )

    assert response.status_code == 422
    assert service_state.artifact_service.list_calls == []


@pytest.mark.asyncio
async def test_synthesize_translates_service_database_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = main.MemoryEngineError(
        "database failed"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 500
    assert response.text == '{"detail":"Database operation failed."}'
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_translates_generation_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = SynthesisEngineError(
        "generation failed"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 502
    assert response.text == '{"detail":"Blueprint generation failed."}'
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_translates_generation_timeout(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.synthesis_service.error = SynthesisTimeoutError(
        "generation timed out"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 504
    assert response.text == '{"detail":"Blueprint generation timed out."}'
    assert service_state.events == [("synthesis_service",)]


@pytest.mark.asyncio
async def test_synthesize_does_not_log_private_database_failure_data(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.synthesis_service.error = main.MemoryEngineError(
        "private-project private-session private-user private brainstorm"
    )

    response = await client.post(
        "/api/synthesize",
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "source_text": "private brainstorm",
        },
    )

    assert response.status_code == 500
    assert response.text == '{"detail":"Database operation failed."}'
    assert service_state.events == [("synthesis_service",)]
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert "private brainstorm" not in caplog.text
    assert "Turns rubrics into executable plans." not in caplog.text


@pytest.mark.parametrize(
    "payload",
    (
        {
            "project_id": " ",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "bad/id",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": " ",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "bad/id",
            "user_id": "user-1",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": " ",
            "source_text": "x",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": " ",
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x" * 10_001,
        },
        {
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "source_text": "x",
            "unexpected": True,
        },
    ),
)
@pytest.mark.asyncio
async def test_synthesize_rejects_invalid_request_before_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    payload: dict[str, object],
) -> None:
    response = await client.post("/api/synthesize", json=payload)

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.parametrize(
    "request_arguments",
    (
        {
            "json": {
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
            }
        },
        {
            "content": "{",
            "headers": {"content-type": "application/json"},
        },
    ),
)
@pytest.mark.asyncio
async def test_synthesize_rejects_incomplete_or_malformed_json(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    request_arguments: dict[str, object],
) -> None:
    response = await client.post(
        "/api/synthesize",
        **request_arguments,
    )

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.asyncio
async def test_chat_decision_uses_updated_profile_and_returns_receipts(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "confirmation-session",
            "user_id": "user-1",
            "message": "Yes, remember that preference.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Generated answer",
        "actions": [
            {
                "action_name": "approve_memory_signal",
                "status": "completed",
            }
            ],
            "artifacts": [],
            "artifact_feedback": [],
            "citations": [],
            "memory_proposals": [],
            "adaptations": [
            {
                "signal_id": "response_length--proposal-1",
                "category": "response_length",
                "value": "concise",
                "source_event_id": (
                    "response_length--proposal-1--approved"
                ),
                "status": "provided_to_model",
            }
        ],
    }
    assert service_state.events == [
        ("history", "confirmation-session", 20),
        (
            "save",
            "confirmation-session",
            "user",
            "Yes, remember that preference.",
        ),
        ("memory_decision",),
        ("turn_service",),
        (
            "save",
            "confirmation-session",
            "model",
            "Generated answer",
        ),
    ]
    assert service_state.memory_service.decision_calls == [
        MemoryDecisionCommand(
            user_id="user-1",
            proposal_id="response_length--proposal-1",
            decision="approve",
            confirmation_channel="chat_decision",
            confirmation_session_id="confirmation-session",
            confirmation_message_id="user-message-1",
        )
    ]
    assert len(service_state.turn_service.calls) == 1
    context = service_state.turn_service.calls[0]
    assert context.message == "Yes, remember that preference."
    context_text = "\n".join(
        part.text
        for content in context.model_input_context
        for part in content.parts
        if part.text
    )
    assert "[APPROVED_COLLABORATION_PREFERENCES]" in context_text
    assert "response_length=concise" in context_text
    assert "response_length--proposal-1" not in context_text
    assert "[SESSION_HISTORY_DATA]" in context_text
    assert context_text.index("Earlier question") < context_text.index(
        "Earlier answer"
    )
    assert "New question" not in context_text
    assert "Yes, remember that preference." not in context_text


@pytest.mark.asyncio
async def test_chat_rejection_returns_action_without_adaptation(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.decision_result = (
        TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="reject_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(),
        )
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "confirmation-session",
            "user_id": "user-1",
            "message": "No, do not remember that.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "reject",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "action_name": "reject_memory_signal",
            "status": "completed",
        }
    ]
    assert response.json()["adaptations"] == []
    assert service_state.memory_service.decision_calls[0].decision == (
        "reject"
    )


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            MemoryProposalNotFoundError("private missing proposal"),
            404,
            "Memory proposal was not found.",
        ),
        (
            MemoryProposalConflictError("private conflicting proposal"),
            409,
            "Memory proposal state conflicts with this request.",
        ),
        (
            MemoryProposalExpiredError("private expired proposal"),
            410,
            "Memory proposal has expired.",
        ),
        (
            ValueError("private invalid proposal identifier"),
            422,
            "Memory decision is invalid.",
        ),
    ),
)
@pytest.mark.asyncio
async def test_chat_decision_maps_domain_errors_before_supervisor(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service_state.memory_service.error = error

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "confirmation-session",
            "user_id": "user-1",
            "message": "Apply my explicit decision.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert service_state.events == [
        ("history", "confirmation-session", 20),
        (
            "save",
            "confirmation-session",
            "user",
            "Apply my explicit decision.",
        ),
        ("memory_decision",),
    ]
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_decision_translates_database_failure_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.memory_service.error = main.MemoryEngineError(
        "private-user private-proposal private-value"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "Approve my private preference.",
            "memory_decision": {
                "proposal_id": "response_length--private-proposal",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert service_state.turn_service.calls == []
    assert "private-user" not in caplog.text
    assert "private-proposal" not in caplog.text
    assert "private-value" not in caplog.text


@pytest.mark.asyncio
async def test_chat_builds_turn_command_and_persists_both_messages(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision_result = service_state.memory_service.decision_result
    assert decision_result is not None
    service_state.database.collaboration_profile = decision_result.profile

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Generated answer",
            "actions": [],
            "artifacts": [],
            "artifact_feedback": [],
            "citations": [],
        "memory_proposals": [],
        "adaptations": [
            {
                "signal_id": "response_length--proposal-1",
                "category": "response_length",
                "value": "concise",
                "source_event_id": (
                    "response_length--proposal-1--approved"
                ),
                "status": "provided_to_model",
            }
        ],
    }
    assert set(service_state.events[:2]) == {
        ("collaboration_profile", "user-1"),
        ("history", "session-1", 20),
    }
    assert service_state.events[2:] == [
        ("save", "session-1", "user", "New question"),
        ("turn_service",),
        ("save", "session-1", "model", "Generated answer"),
    ]

    assert len(service_state.turn_service.calls) == 1
    context = service_state.turn_service.calls[0]
    assert context.project_id == "project-1"
    assert context.session_id == "session-1"
    assert context.user_id == "user-1"
    assert context.message == "New question"
    assert context.recent_user_messages == ("Earlier question",)
    assert len(context.model_input_context) == 1
    context_content = context.model_input_context[0]
    assert context_content.role == "user"
    context_text = context_content.parts[0].text
    assert "[APPROVED_COLLABORATION_PREFERENCES]" in context_text
    assert "response_length=concise" in context_text
    assert "response_length--proposal-1" not in context_text


@pytest.mark.asyncio
async def test_headerless_chat_returns_proposal_from_persisted_source_message(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--proposal-1",
        category="response_length",
        proposed_value="concise",
        expires_at=MEMORY_NOW + timedelta(hours=24),
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="I created a pending proposal for your review.",
        actions=(
            AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
        ),
        memory_proposals=(proposal,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Please remember that I prefer concise responses.",
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "action_name": "propose_memory_signal",
            "status": "completed",
        }
    ]
    assert response.json()["memory_proposals"] == [
        proposal.model_dump(mode="json")
    ]
    context = service_state.turn_service.calls[0]
    assert context.source_message_id == "user-message-1"
    assert context.memory_decision_present is False
    assert context.turn_lease is None
    assert context.precompleted_actions == ()
    assert context.precompleted_memory_proposals == ()


@pytest.mark.parametrize(
    "idempotency_key",
    (
        "",
        "bad/key",
        "bad.key",
        "contains space",
        "bad$key",
        "a" * 129,
    ),
)
@pytest.mark.asyncio
async def test_chat_rejects_invalid_idempotency_key_before_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    idempotency_key: str,
) -> None:
    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": idempotency_key},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Idempotency key is invalid."}
    assert service_state.events == []
    assert service_state.memory_service.decision_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_rejects_oversized_message_before_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "x" * 10_001,
        },
    )

    assert response.status_code == 422
    assert service_state.events == []
    assert service_state.memory_service.decision_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_accepts_message_at_exact_upper_bound(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    message = "x" * 10_000

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": message,
        },
    )

    assert response.status_code == 200
    assert service_state.turn_service.calls[0].message == message


@pytest.mark.asyncio
async def test_chat_replays_completed_idempotent_turn_without_downstream_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    stored_response = ChatResponse(
        response="Stored answer",
        actions=[
            AgentActionReceipt(
                action_name="synthesize_project",
                status="completed",
            )
        ],
        artifacts=[
            ArtifactReference(
                artifact_type="synthesis_blueprint",
                project_id="project-1",
                artifact_id="blueprint-1",
                schema_version="2.0",
                display_label="Stored blueprint",
            )
        ],
        citations=[
            CitationReference(
                uri="https://example.com/evidence",
                label="Stored evidence",
            )
        ],
        adaptations=[
            AdaptationReceipt(
                signal_id="response_length--signal-1",
                category="response_length",
                value="concise",
                source_event_id="response_length--signal-1--approved",
                status="provided_to_model",
            )
        ],
    )
    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "replay-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 200
    assert response.json() == stored_response.model_dump(mode="json")
    assert service_state.events == [("claim_chat_turn",)]
    assert service_state.memory_service.decision_calls == []
    assert service_state.turn_service.calls == []
    assert service_state.database.renew_calls == []
    assert service_state.database.release_calls == []
    assert service_state.database.complete_calls == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail", "retry_after"),
    (
        (
            ChatTurnConflictError("private-conflict-marker"),
            409,
            "Idempotency key conflicts with a different chat request.",
            None,
        ),
        (
            ChatTurnInProgressError(17),
            409,
            "Chat turn is already in progress.",
            "17",
        ),
        (
            ChatTurnStateError("private-state-marker"),
            500,
            "Chat turn state is invalid.",
            None,
        ),
        (
            main.MemoryEngineError("private-database-marker"),
            500,
            "Database operation failed.",
            None,
        ),
    ),
)
@pytest.mark.asyncio
async def test_chat_translates_idempotent_claim_errors_without_downstream_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_status: int,
    expected_detail: str,
    retry_after: str | None,
) -> None:
    service_state.database.chat_turn_error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "private-key-1"},
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "private-message-marker",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    if retry_after is None:
        assert "Retry-After" not in response.headers
    else:
        assert response.headers["Retry-After"] == retry_after
    assert service_state.events == [("claim_chat_turn",)]
    assert service_state.memory_service.decision_calls == []
    assert service_state.turn_service.calls == []
    assert service_state.database.renew_calls == []
    assert service_state.database.release_calls == []
    assert service_state.database.complete_calls == []
    for private_marker in (
        "private-key-1",
        "private-project",
        "private-session",
        "private-user",
        "private-message-marker",
        "private-conflict-marker",
        "private-state-marker",
        "private-database-marker",
    ):
        assert private_marker not in caplog.text


@pytest.mark.asyncio
async def test_chat_completes_claimed_turn_without_duplicate_message_writes(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    renewed_claim = ChatTurnClaim(
        request=claim.request,
        ids=claim.ids,
        owner_token=claim.owner_token,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
        resumed=claim.resumed,
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    expected_response = ChatResponse(
        response="Generated answer",
        actions=[],
        artifacts=[],
        citations=[],
        adaptations=[],
    )
    assert response.json() == expected_response.model_dump(mode="json")
    assert service_state.events[0] == ("claim_chat_turn",)
    assert set(service_state.events[1:3]) == {
        ("collaboration_profile", "user-1"),
        (
            "history",
            "session-1",
            20,
            f"turn--{DEFAULT_TURN_ID}--user",
        ),
    }
    assert service_state.events[3:] == [
        ("renew_chat_turn_lease",),
        ("turn_service",),
        ("complete_chat_turn",),
    ]
    assert not any(event[0] == "save" for event in service_state.events)
    assert len(service_state.database.claim_calls) == 1
    turn_request, key, observed_at = service_state.database.claim_calls[0]
    assert turn_request == claim.request
    assert key == "owned-key-1"
    assert observed_at.tzinfo is not None
    assert service_state.database.renew_calls[0][0] == claim
    assert service_state.database.complete_calls == [
        (
            renewed_claim,
            expected_response,
            service_state.database.complete_calls[0][2],
        )
    ]
    assert service_state.database.complete_calls[0][2].tzinfo is not None
    assert len(service_state.turn_service.calls) == 1
    context = service_state.turn_service.calls[0]
    assert context.message == "New question"
    context_text = "\n".join(
        part.text
        for content in context.model_input_context
        for part in content.parts
        if part.text
    )
    assert "Earlier question" in context_text
    assert "Earlier answer" in context_text
    assert "New question" not in context_text


@pytest.mark.asyncio
async def test_chat_completes_artifact_turn_with_refreshed_claim_and_receipts(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    renewed_claim = replace(
        claim,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
    )
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="project-1",
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
    effect_claim = replace(
        renewed_claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Created the requested collaborative blueprint.",
        actions=(action,),
        artifacts=(artifact,),
        adaptations=(adaptation,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-cutover-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert service_state.turn_service.calls[0].chat_turn_claim is (
        renewed_claim
    )
    assert response.json()["actions"] == [action.model_dump(mode="json")]
    assert response.json()["artifacts"] == [
        artifact.model_dump(mode="json")
    ]
    assert response.json()["adaptations"] == [
        adaptation.model_dump(mode="json")
    ]
    assert service_state.database.complete_calls[0][0] is effect_claim
    stored_response = service_state.database.complete_calls[0][1]
    assert stored_response.model_dump(mode="json") == response.json()


@pytest.mark.asyncio
async def test_artifact_responder_failure_releases_refreshed_claim_and_receipts(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    renewed_claim = replace(
        claim,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
    )
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id="project-1",
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
    effect_claim = replace(
        renewed_claim,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.database.released_claim = replace(
        effect_claim,
        resumed=True,
    )
    service_state.turn_service.error = AgentColTurnResponderError(
        "private responder failure",
        actions=(action,),
        artifacts=(artifact,),
        adaptations=(adaptation,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Agent_Col response failed after a completed action.",
        "actions": [action.model_dump(mode="json")],
        "artifacts": [artifact.model_dump(mode="json")],
        "memory_proposals": [],
        "adaptations": [adaptation.model_dump(mode="json")],
    }
    assert service_state.database.release_calls[0][0] is effect_claim
    assert service_state.database.complete_calls == []


@pytest.mark.asyncio
async def test_chat_requires_idempotency_key_for_artifact_feedback(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "I accept this blueprint boundary.",
            "artifact_feedback_decision": {
                "artifact_id": "blueprint-1",
                "target_id": "target--0123456789abcdef01234567",
                "decision": "accepted",
                "feedback_text": "This boundary is correct.",
                "expected_schema_version": "2.0",
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Artifact feedback requires an idempotency key."
    }
    assert service_state.events == []


@pytest.mark.asyncio
async def test_chat_completes_structured_artifact_feedback_turn(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    claim = make_chat_turn_claim(artifact_feedback_decision=decision)
    renewed_claim = replace(
        claim,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
    )
    action = AgentActionReceipt(
        action_name="record_blueprint_feedback",
        status="completed",
    )
    feedback = ArtifactFeedbackReference(
        feedback_id=f"feedback--{claim.ids.turn_id}",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=MEMORY_NOW,
    )
    effect_claim = replace(
        renewed_claim,
        precompleted_actions=(action,),
        precompleted_artifact_feedback=(feedback,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="I recorded your artifact feedback.",
        actions=(action,),
        artifact_feedback=(feedback,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [action.model_dump(mode="json")]
    assert response.json()["artifact_feedback"] == [
        feedback.model_dump(mode="json")
    ]
    turn_request = service_state.database.claim_calls[0][0]
    assert turn_request.artifact_feedback_decision == decision
    command = service_state.turn_service.calls[0]
    assert command.artifact_feedback_decision_present is True
    assert command.chat_turn_claim is renewed_claim
    assert service_state.database.complete_calls[0][0] is effect_claim
    assert service_state.database.complete_calls[0][1].artifact_feedback == [
        feedback
    ]


@pytest.mark.asyncio
async def test_feedback_responder_failure_returns_completed_receipt(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    claim = make_chat_turn_claim(artifact_feedback_decision=decision)
    action = AgentActionReceipt(
        action_name="record_blueprint_feedback",
        status="completed",
    )
    feedback = ArtifactFeedbackReference(
        feedback_id=f"feedback--{claim.ids.turn_id}",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=MEMORY_NOW,
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_artifact_feedback=(feedback,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.released_claim = effect_claim
    service_state.turn_service.error = AgentColTurnResponderError(
        "private responder failure",
        actions=(action,),
        artifact_feedback=(feedback,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 502
    assert response.json()["actions"] == [action.model_dump(mode="json")]
    assert response.json()["artifact_feedback"] == [
        feedback.model_dump(mode="json")
    ]
    assert service_state.database.complete_calls == []


@pytest.mark.asyncio
async def test_feedback_missing_target_returns_safe_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        artifact_feedback_decision=decision
    )
    cause = ArtifactFeedbackTargetNotFoundError("private target locator")
    error = AgentColTurnServiceError(
        "Agent_Col artifact feedback execution failed."
    )
    error.__cause__ = cause
    service_state.turn_service.error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-missing-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Blueprint artifact or feedback target was not found."
    }
    assert "private target locator" not in response.text


@pytest.mark.asyncio
async def test_feedback_stale_schema_returns_safe_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        artifact_feedback_decision=decision
    )
    cause = ArtifactFeedbackSchemaConflictError("private schema state")
    error = AgentColTurnServiceError(
        "Agent_Col artifact feedback execution failed."
    )
    error.__cause__ = cause
    service_state.turn_service.error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-conflict-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Artifact feedback conflicts with the current artifact state."
    }
    assert "private schema state" not in response.text


@pytest.mark.asyncio
async def test_feedback_ledger_conflict_returns_safe_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        artifact_feedback_decision=decision
    )
    cause = BlueprintFeedbackConflictError("private ledger state")
    error = AgentColTurnServiceError(
        "Agent_Col artifact feedback execution failed."
    )
    error.__cause__ = cause
    service_state.turn_service.error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-ledger-conflict-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Artifact feedback conflicts with the current artifact state."
    }
    assert "private ledger state" not in response.text


@pytest.mark.asyncio
async def test_feedback_invalid_state_returns_safe_internal_error(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        artifact_feedback_decision=decision
    )
    cause = ArtifactFeedbackStateError("private inconsistent receipt")
    error = AgentColTurnServiceError(
        "Agent_Col artifact feedback execution failed."
    )
    error.__cause__ = cause
    service_state.turn_service.error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-state-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Artifact feedback state is invalid."}
    assert "private inconsistent receipt" not in response.text


@pytest.mark.asyncio
async def test_feedback_ledger_invalid_state_returns_safe_internal_error(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = ArtifactFeedbackDecisionRequest(
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        decision="accepted",
        feedback_text="This boundary is correct.",
        expected_schema_version="2.0",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        artifact_feedback_decision=decision
    )
    cause = BlueprintFeedbackStateError("private ledger receipt")
    error = AgentColTurnServiceError(
        "Agent_Col artifact feedback execution failed."
    )
    error.__cause__ = cause
    service_state.turn_service.error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-feedback-ledger-state-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "artifact_feedback_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Artifact feedback state is invalid."}
    assert "private ledger receipt" not in response.text


@pytest.mark.asyncio
async def test_chat_replays_completed_expert_receipts_without_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    action = AgentActionReceipt(
        action_name="url_context",
        status="completed",
    )
    citation = CitationReference(
        uri="https://example.com/evidence",
        label="Example evidence",
    )
    service_state.database.chat_turn_result = claim
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Evidence-backed answer",
        actions=(action,),
        citations=(citation,),
    )
    headers = {"Idempotency-Key": "expert-replay-key-1"}
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "Analyze https://example.com/evidence",
    }

    first_response = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 200
    stored_response = service_state.database.complete_calls[0][1]
    assert stored_response.actions == [action]
    assert stored_response.citations == [citation]
    assert len(service_state.turn_service.calls) == 1

    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )
    event_count = len(service_state.events)

    replay_response = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert replay_response.status_code == 200
    assert replay_response.json() == first_response.json()
    assert service_state.events[event_count:] == [("claim_chat_turn",)]
    assert len(service_state.turn_service.calls) == 1
    assert len(service_state.database.complete_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action_name", "response_text", "idempotency_key", "message"),
    (
        (
            "run_computation",
            "The verified mean is 19.5.",
            "computation-replay-key-1",
            "Calculate the mean of 12, 15, 18, 21, 24, and 27.",
        ),
        (
            "verify_requirements",
            "One requirement is covered and one is contradictory.",
            "verification-replay-key-1",
            (
                "Compare the supplied draft against every supplied "
                "requirement."
            ),
        ),
    ),
)
async def test_chat_replays_completed_cognitive_action_without_reexecution(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    action_name: str,
    response_text: str,
    idempotency_key: str,
    message: str,
) -> None:
    claim = make_chat_turn_claim()
    action = AgentActionReceipt(
        action_name=action_name,
        status="completed",
    )
    service_state.database.chat_turn_result = claim
    service_state.turn_service.turn_result = AgentColTurnResult(
        response=response_text,
        actions=(action,),
    )
    headers = {"Idempotency-Key": idempotency_key}
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": message,
    }

    first_response = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 200
    stored_response = service_state.database.complete_calls[0][1]
    assert stored_response.actions == [action]
    assert stored_response.citations == []
    assert len(service_state.turn_service.calls) == 1

    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )
    event_count = len(service_state.events)

    replay_response = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert replay_response.status_code == 200
    assert replay_response.json() == first_response.json()
    assert service_state.events[event_count:] == [("claim_chat_turn",)]
    assert len(service_state.turn_service.calls) == 1
    assert len(service_state.database.complete_calls) == 1


@pytest.mark.asyncio
async def test_resumed_idempotent_chat_supplies_owned_precompleted_effects(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    turn_id = "a" * 64
    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = MemoryProposalReceipt(
        proposal_id="response_length--proposal-1",
        category="response_length",
        proposed_value="concise",
        expires_at=MEMORY_NOW + timedelta(hours=24),
    )
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="Remember my preference.",
        ),
        ids=ChatTurnIds(
            turn_id=turn_id,
            user_message_id=f"turn--{turn_id}--user",
            model_message_id=f"turn--{turn_id}--model",
        ),
        owner_token="owner-token-1",
        lease_expires_at=MEMORY_NOW + timedelta(seconds=120),
        resumed=True,
        precompleted_actions=(action,),
        precompleted_memory_proposals=(proposal,),
    )
    service_state.database.chat_turn_result = claim
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Your proposal remains pending.",
        actions=(action,),
        memory_proposals=(proposal,),
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "resumed-proposal-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Remember my preference.",
        },
    )

    assert response.status_code == 200
    context = service_state.turn_service.calls[0]
    assert context.source_message_id == f"turn--{turn_id}--user"
    assert context.turn_lease == ProposalTurnLease(
        turn_id=turn_id,
        owner_token="owner-token-1",
    )
    assert context.precompleted_actions == (action,)
    assert context.precompleted_memory_proposals == (proposal,)
    assert response.json()["memory_proposals"] == [
        proposal.model_dump(mode="json")
    ]


@pytest.mark.asyncio
async def test_chat_claimed_turn_starts_context_reads_concurrently(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = claim
    profile_started = asyncio.Event()
    history_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_profile(
        user_id: str,
    ) -> CollaborationProfile:
        assert user_id == "user-1"
        profile_started.set()
        await release.wait()
        return CollaborationProfile()

    async def blocked_history(
        session_id: str,
        limit: int | None = None,
        *,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        assert exclude_message_id == f"turn--{DEFAULT_TURN_ID}--user"
        history_started.set()
        await release.wait()
        return []

    service_state.database.get_collaboration_profile = blocked_profile
    service_state.database.get_chat_history = blocked_history
    request_task = asyncio.create_task(
        client.post(
            "/api/chat",
            headers={"Idempotency-Key": "concurrent-key-1"},
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": "New question",
            },
        )
    )

    await asyncio.wait_for(profile_started.wait(), timeout=1)
    both_reads_started = True
    try:
        await asyncio.wait_for(history_started.wait(), timeout=1)
    except TimeoutError:
        both_reads_started = False
    finally:
        assert service_state.turn_service.calls == []
        release.set()
        response = await request_task

    assert both_reads_started
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_idempotent_decision_uses_deterministic_confirmation_message_id(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    memory_decision = MemoryDecisionRequest(
        proposal_id="response_length--proposal-1",
        decision="approve",
    )
    claim = ChatTurnClaim(
        request=ChatTurnRequest(
            project_id="project-1",
            session_id="confirmation-session",
            user_id="user-1",
            message="Yes, remember that preference.",
            memory_decision=memory_decision,
        ),
        ids=ChatTurnIds(
            turn_id="c" * 64,
            user_message_id=f"turn--{'c' * 64}--user",
            model_message_id=f"turn--{'c' * 64}--model",
        ),
        owner_token="decision-owner-token",
        lease_expires_at=MEMORY_NOW + timedelta(seconds=120),
        resumed=False,
    )
    service_state.database.chat_turn_result = claim
    completed_action = AgentActionReceipt(
        action_name="approve_memory_signal",
        status="completed",
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Generated answer",
        actions=(completed_action,),
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "decision-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "confirmation-session",
            "user_id": "user-1",
            "message": "Yes, remember that preference.",
            "memory_decision": memory_decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "action_name": "approve_memory_signal",
            "status": "completed",
        }
    ]
    assert response.json()["adaptations"] == [
        {
            "signal_id": "response_length--proposal-1",
            "category": "response_length",
            "value": "concise",
            "source_event_id": (
                "response_length--proposal-1--approved"
            ),
            "status": "provided_to_model",
        }
    ]
    assert service_state.events == [
        ("claim_chat_turn",),
        (
            "history",
            "confirmation-session",
            20,
            f"turn--{'c' * 64}--user",
        ),
        ("memory_decision",),
        ("record_chat_turn_decision_action",),
        ("renew_chat_turn_lease",),
        ("turn_service",),
        ("complete_chat_turn",),
    ]
    assert service_state.memory_service.decision_calls == [
        MemoryDecisionCommand(
            user_id="user-1",
            proposal_id="response_length--proposal-1",
            decision="approve",
            confirmation_channel="chat_decision",
            confirmation_session_id="confirmation-session",
            confirmation_message_id=f"turn--{'c' * 64}--user",
        )
    ]
    assert len(service_state.database.decision_action_calls) == 1
    recorded_claim, recorded_action, recorded_at = (
        service_state.database.decision_action_calls[0]
    )
    assert recorded_claim == claim
    decision_result = service_state.memory_service.decision_result
    assert decision_result is not None
    assert recorded_action == decision_result.action
    assert recorded_at.tzinfo is not None
    assert not any(event[0] == "save" for event in service_state.events)
    assert len(service_state.database.complete_calls) == 1
    completed_response = service_state.database.complete_calls[0][1]
    assert completed_response.model_dump(mode="json") == response.json()


@pytest.mark.parametrize(
    ("failure_operation", "error", "expected_status", "expected_detail"),
    (
        (
            "renew",
            ChatTurnOwnershipError("private-renew-owner-marker"),
            409,
            (
                "Chat turn ownership changed; retry with the same "
                "idempotency key."
            ),
        ),
        (
            "complete",
            ChatTurnOwnershipError("private-complete-owner-marker"),
            409,
            (
                "Chat turn ownership changed; retry with the same "
                "idempotency key."
            ),
        ),
        (
            "renew",
            ChatTurnStateError("private-renew-state-marker"),
            500,
            "Chat turn state is invalid.",
        ),
        (
            "complete",
            ChatTurnStateError("private-complete-state-marker"),
            500,
            "Chat turn state is invalid.",
        ),
        (
            "renew",
            main.MemoryEngineError("private-renew-database-marker"),
            500,
            "Database operation failed.",
        ),
        (
            "complete",
            main.MemoryEngineError("private-complete-database-marker"),
            500,
            "Database operation failed.",
        ),
    ),
)
@pytest.mark.asyncio
async def test_chat_translates_owned_turn_persistence_errors_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    failure_operation: str,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = claim
    if failure_operation == "renew":
        service_state.database.renew_error = error
    else:
        service_state.database.complete_error = error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "private-owned-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert not any(event[0] == "save" for event in service_state.events)
    if failure_operation == "renew":
        assert service_state.turn_service.calls == []
        assert service_state.database.complete_calls == []
    else:
        assert len(service_state.turn_service.calls) == 1
        assert len(service_state.database.complete_calls) == 1
    assert service_state.database.release_calls == []
    for private_marker in (
        "private-owned-key",
        "owner-token-1",
        "project-1",
        "session-1",
        "user-1",
        "New question",
        "Generated answer",
        str(error),
    ):
        assert private_marker not in caplog.text


@pytest.mark.parametrize(
    ("turn_error", "expected_status", "expected_detail"),
    (
        (
            AgentColTurnRoutingError("routing failed"),
            502,
            "Agent_Col response failed.",
        ),
        (
            AgentColTurnRoutingTimeoutError("routing timed out"),
            504,
            "Agent_Col response timed out.",
        ),
        (
            AgentColTurnResponderError("responder failed"),
            502,
            "Agent_Col response failed.",
        ),
        (
            AgentColTurnTimeoutError("turn timed out"),
            504,
            "Agent_Col response timed out.",
        ),
        (
            AgentColTurnServiceError("turn failed"),
            502,
            "Agent_Col response failed.",
        ),
    ),
)
@pytest.mark.asyncio
async def test_chat_releases_claim_after_turn_service_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    turn_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    claim = make_chat_turn_claim()
    renewed_claim = ChatTurnClaim(
        request=claim.request,
        ids=claim.ids,
        owner_token=claim.owner_token,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
        resumed=claim.resumed,
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.turn_service.error = turn_error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "provider-failure-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert len(service_state.database.renew_calls) == 1
    assert len(service_state.turn_service.calls) == 1
    assert len(service_state.database.release_calls) == 1
    assert service_state.database.release_calls[0][0] == renewed_claim
    assert service_state.database.release_calls[0][1].tzinfo is not None
    assert service_state.database.complete_calls == []
    assert not any(event[0] == "save" for event in service_state.events)


@pytest.mark.parametrize(
    ("turn_error_type", "expected_status", "expected_detail"),
    (
        (
            AgentColTurnResponderError,
            502,
            "Agent_Col response failed after a completed action.",
        ),
        (
            AgentColTurnTimeoutError,
            504,
            "Agent_Col response timed out after a completed action.",
        ),
    ),
)
@pytest.mark.asyncio
async def test_headerless_chat_returns_completed_effects_on_provider_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    turn_error_type: type[AgentColTurnServiceError],
    expected_status: int,
    expected_detail: str,
) -> None:
    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = make_memory_proposal_receipt()
    service_state.turn_service.error = turn_error_type(
        "private provider failure",
        actions=(action,),
        memory_proposals=(proposal,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Remember this preference.",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": expected_detail,
        "actions": [action.model_dump(mode="json")],
        "memory_proposals": [proposal.model_dump(mode="json")],
    }
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_idempotent_failure_recovers_completed_effects_from_turn_ledger(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = make_memory_proposal_receipt()
    claim = make_chat_turn_claim(resumed=True)
    service_state.database.chat_turn_result = claim
    service_state.database.released_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_memory_proposals=(proposal,),
    )
    service_state.turn_service.error = AgentColTurnResponderError(
        "private provider failure"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "recover-completed-effects"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Agent_Col response failed after a completed action.",
        "actions": [action.model_dump(mode="json")],
        "memory_proposals": [proposal.model_dump(mode="json")],
    }
    assert len(service_state.database.release_calls) == 1
    assert service_state.database.complete_calls == []


@pytest.mark.parametrize(
    ("cause", "expected_status", "expected_detail"),
    (
        (
            MemoryProposalOriginConflictError("private origin conflict"),
            409,
            "Memory proposal state conflicts with this request.",
        ),
        (
            MemoryProposalConflictError("private category conflict"),
            409,
            "Memory proposal state conflicts with this request.",
        ),
        (
            MemoryProposalStateError("private stored state"),
            500,
            "Memory proposal state is invalid.",
        ),
        (
            main.MemoryEngineError("private database failure"),
            500,
            "Database operation failed.",
        ),
        (
            ChatTurnOwnershipError("private turn ownership"),
            409,
            (
                "Chat turn ownership changed; retry with the same "
                "idempotency key."
            ),
        ),
    ),
)
@pytest.mark.asyncio
async def test_chat_maps_governed_proposal_tool_failures_by_typed_cause(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    cause: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    runtime_error = SupervisorRuntimeError("private runtime wrapper")
    runtime_error.__cause__ = cause
    turn_error = AgentColTurnResponderError("responder failed")
    turn_error.__cause__ = runtime_error
    service_state.turn_service.error = turn_error

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Remember this preference.",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert str(cause) not in caplog.text
    assert "private runtime wrapper" not in caplog.text


@pytest.mark.parametrize(
    "release_error",
    (
        main.MemoryEngineError("private-release-database-marker"),
        ChatTurnOwnershipError("private-release-owner-error-marker"),
        ChatTurnStateError("private-release-state-marker"),
        ValueError("private-release-value-marker"),
    ),
)
@pytest.mark.asyncio
async def test_chat_release_failure_does_not_replace_turn_service_error(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    release_error: Exception,
) -> None:
    claim = make_chat_turn_claim(owner_token="private-owner-marker")
    service_state.database.chat_turn_result = claim
    service_state.turn_service.error = AgentColTurnResponderError(
        "private-provider-marker"
    )
    service_state.database.release_error = release_error

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "private-release-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Agent_Col response failed."}
    assert len(service_state.database.release_calls) == 1
    assert service_state.database.complete_calls == []
    for private_marker in (
        "private-owner-marker",
        "private-provider-marker",
        str(release_error),
        "private-release-key",
        "project-1",
        "session-1",
        "user-1",
        "New question",
    ):
        assert private_marker not in caplog.text


@pytest.mark.parametrize(
    "field",
    ("project_id", "session_id", "user_id", "message"),
)
@pytest.mark.asyncio
async def test_chat_rejects_whitespace_only_fields(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    field: str,
) -> None:
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "hello",
    }
    payload[field] = " \t "

    response = await client.post("/api/chat", json=payload)

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.parametrize(
    "request_arguments",
    (
        {
            "json": {
                "project_id": "project-1",
                "session_id": "session-1",
                "message": "hello",
            }
        },
        {
            "content": "{",
            "headers": {"content-type": "application/json"},
        },
        {
            "content": "not-json",
            "headers": {"content-type": "text/plain"},
        },
        {
            "json": {
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": "Remember this.",
                "memory_decision": {
                    "proposal_id": "response_length--proposal-1",
                    "decision": "yes",
                },
            }
        },
    ),
)
@pytest.mark.asyncio
async def test_chat_rejects_invalid_json_payloads(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    request_arguments: dict[str, object],
) -> None:
    response = await client.post("/api/chat", **request_arguments)

    assert response.status_code == 422
    assert service_state.events == []


@pytest.mark.parametrize(
    "failure_point",
    ("profile", "history", "save_user", "save_model"),
)
@pytest.mark.asyncio
async def test_chat_translates_database_failures(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    failure_point: str,
) -> None:
    service_state.database.fail_on = failure_point

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "private message",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}


@pytest.mark.asyncio
async def test_chat_translates_turn_service_failure_without_model_write(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_message = "private prompt text"
    service_state.turn_service.error = AgentColTurnResponderError(
        f"provider echoed {private_message}"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": private_message,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Agent_Col response failed."}
    assert private_message not in caplog.text
    assert "private-project" not in caplog.text
    assert "private-session" not in caplog.text
    assert "private-user" not in caplog.text
    assert (
        "save",
        "private-session",
        "user",
        private_message,
    ) in service_state.events
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_chat_translates_turn_timeout_without_model_write(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.turn_service.error = AgentColTurnTimeoutError(
        "turn timed out"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 504
    assert response.json() == {"detail": "Agent_Col response timed out."}
    assert (
        "save",
        "session-1",
        "user",
        "Hello",
    ) in service_state.events
    assert not any(
        event[0] == "save" and event[2] == "model"
        for event in service_state.events
    )


@pytest.mark.asyncio
async def test_chat_starts_context_reads_concurrently(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    profile_started = asyncio.Event()
    history_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_profile(
        user_id: str,
    ) -> CollaborationProfile:
        assert user_id == "user-1"
        profile_started.set()
        await release.wait()
        return CollaborationProfile()

    async def blocked_history(
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        history_started.set()
        await release.wait()
        return []

    service_state.database.get_collaboration_profile = blocked_profile
    service_state.database.get_chat_history = blocked_history
    request_task = asyncio.create_task(
        client.post(
            "/api/chat",
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": "Hello",
            },
        )
    )

    await asyncio.wait_for(profile_started.wait(), timeout=1)
    both_reads_started = True
    try:
        await asyncio.wait_for(history_started.wait(), timeout=1)
    except TimeoutError:
        both_reads_started = False
    finally:
        assert ("turn_service",) not in service_state.events
        release.set()
        response = await request_task

    assert both_reads_started
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_rejects_invalid_stored_history_before_writes(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.history = [
        {"role": "tool", "text": "untrusted content"}
    ]

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Hello",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Chat history is invalid."}
    assert not any(event[0] == "save" for event in service_state.events)
    assert ("turn_service",) not in service_state.events


@pytest.mark.asyncio
async def test_lifespan_closes_both_clients(
    service_state: ServiceState,
) -> None:
    assert not service_state.database.closed
    assert not service_state.genai_client.aio.closed
    assert not service_state.genai_client.closed

    async with main.lifespan(main.app):
        assert not service_state.database.closed

    assert service_state.database.closed
    assert service_state.genai_client.aio.closed
    assert service_state.genai_client.closed
