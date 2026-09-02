import asyncio
import hashlib
import json
import logging
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
    RecordBlueprintFeedbackCommand,
    RecordBlueprintFeedbackResult,
)
from artifact_read_service import (
    ArtifactReadService,
    ArtifactReadStateError,
    GetBlueprintArtifactCommand,
    ListBlueprintArtifactsCommand,
)
from generic_artifact_service import (
    ArchiveGenericArtifactCommand,
    ArtifactReadStateError as GenericArtifactReadStateError,
    CreateGenericArtifactVersionCommand,
    DeleteGenericArtifactCommand,
    GetGenericArtifactCommand,
    ListGenericArtifactsCommand,
    RestoreGenericArtifactCommand,
    UpdateGenericArtifactMetadataCommand,
)
from generic_artifact_creation_service import (
    GenericArtifactCreationCommand,
    GenericArtifactCreationResult,
    GenericArtifactCreationService,
)
from generic_artifact_generation import (
    GenericArtifactGenerationError,
    GenericArtifactGenerationRequest,
    GenericArtifactGenerationTimeoutError,
    generate_generic_artifact,
)
from agent_col_agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobFailure,
    AgentJobReport,
)
from agent_job_repository import (
    AgentJobConflictError,
    AgentJobNotFoundError,
    AgentJobRepositoryError,
    AgentJobStateError,
)
from agent_col_turn_service import (
    AgentColTextDelta,
    AgentColTurnCommand,
    AgentColTurnCompleted,
    AgentColTurnResponderError,
    AgentColTurnResult,
    AgentColTurnRoutingError,
    AgentColTurnRoutingTimeoutError,
    AgentColTurnServiceError,
    AgentColTurnTimeoutError,
)
from auth import AuthSettings, Authenticator
from auth import google_subject_to_workspace_project_id
from chat_turns import (
    ChatTurnClaim,
    ChatTurnConflictError,
    ChatTurnIds,
    ChatTurnInProgressError,
    ChatTurnOwnershipError,
    ChatTurnReplay,
    ChatTurnRequest,
    ChatSessionOwnershipError,
    ChatTurnStateError,
)
from continuity import ContinuityResolution, ContinuitySourceText
from continuity_service import ContinuityResolutionCommand, ContinuityService
from database import (
    ArtifactCursorNotFoundError,
    ArtifactNotFoundError,
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
    MemoryClarificationSelectionError,
    MemoryClarificationStateError,
    MemorySignalConflictError,
    MemorySignalNotFoundError,
    WorkspaceDeletionConflictError,
    WorkspaceNotFoundError,
)
from speech_service import (
    SpeechTranscriptionProviderError,
    SpeechSynthesisChunkError,
    SpeechSynthesisProviderError,
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
    ChatMessageRecord,
    ChatResponse,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
    CitationReference,
    CollaborationProfile,
    CollaborativeNote,
    CollaborativeNoteCorrectionRequest,
    CollaborativeNoteDecisionRequest,
    CollaborativeNoteDetailResponse,
    CollaborativeNoteEvent,
    CollaborativeNoteLifecycleResponse,
    CollaborativeNoteListResponse,
    CollaborativeNoteMutationRequest,
    CollaborativeNoteProposalRequest,
    CollaborativeNoteProposal,
    CollaborativeNoteProposalResponse,
    ContinuityChoice,
    ContinuitySelectionRequest,
    ContinuitySourceReceipt,
    MemoryDecisionRequest,
    MemoryClarificationChoice,
    MemoryClarificationReceipt,
    MemoryClarificationSelectionRequest,
    MemoryEvent,
    MemoryProposal,
    MemoryProposalReceipt,
    MemoryProposalReceiptV2,
    QueuedActionReceipt,
    SingleFileArtifact,
    SingleFileArtifactCreateResponse,
    SingleFileArtifactDetailResponse,
    SingleFileArtifactEditRequest,
    SingleFileArtifactLifecycleResponse,
    SingleFileArtifactListResponse,
    SingleFileArtifactMetadataUpdateRequest,
    SingleFileArtifactMetadata,
    SynthesisBlueprint,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceSummary,
)
from collaborative_note_service import (
    CollaborativeNoteCorrectionCommand,
    CollaborativeNoteProposalCommand,
    CollaborativeNoteDecisionCommand,
    CollaborativeNoteDecisionResult,
    CollaborativeNoteDeletionResult,
    CollaborativeNoteDetailResult,
    CollaborativeNoteLifecycleCommand,
    CollaborativeNoteLifecycleResult,
    CollaborativeNoteListResult,
    CollaborativeNoteProposalResult,
    GetCollaborativeNoteCommand,
    ListCollaborativeNotesCommand,
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
    NaturalMemoryClarificationResult,
    NaturalMemoryCommand,
    NaturalMemoryProposalResult,
    RevokeMemorySignalCommand,
    SelectMemoryClarificationCommand,
    TrustedMemoryInspectionResult,
    TrustedMemoryMutationResult,
)
from vertex_config import VertexAISettings
from working_state import WorkingStateSnapshot
from working_state_service import WorkingStateUpdateInput, WorkingStateUpdateResult


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


def public_user_locator(subject: str) -> str:
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
    return f"user--{digest}"


def make_chat_turn_claim(
    *,
    memory_decision: MemoryDecisionRequest | None = None,
    memory_clarification_selection: (
        MemoryClarificationSelectionRequest | None
    ) = None,
    continuity_selection: ContinuitySelectionRequest | None = None,
    artifact_feedback_decision: ArtifactFeedbackDecisionRequest | None = None,
    collaborative_note_decision: CollaborativeNoteDecisionRequest | None = None,
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
            memory_clarification_selection=memory_clarification_selection,
            continuity_selection=continuity_selection,
            artifact_feedback_decision=artifact_feedback_decision,
            collaborative_note_decision=collaborative_note_decision,
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


def make_memory_clarification_receipt() -> MemoryClarificationReceipt:
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
        expires_at=MEMORY_NOW + timedelta(minutes=15),
    )


def make_continuity_receipt() -> ContinuitySourceReceipt:
    return ContinuitySourceReceipt(
        receipt_id="continuity--note-export--rev-2",
        source_kind="collaborative_note",
        source_id="note-export",
        display_label="Used note: Export workflow",
        match_reason="exact_title",
        source_updated_at=MEMORY_NOW,
    )


def make_agent_job(**overrides: object) -> AgentJob:
    values: dict[str, object] = {
        "job_id": "agent-job-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "project-1",
        "session_id": "session-1",
        "source_turn_id": "turn-1",
        "source_message_id": "message-1",
        "action_kind": "create_artifact",
        "status": "queued",
        "display_label": "Create deployment artifact",
        "agent_label": "Artifact Builder",
        "created_at": MEMORY_NOW,
        "updated_at": MEMORY_NOW,
        "idempotency_key": "private-idempotency-key",
        "attempt_count": 1,
        "lease_owner": None,
        "lease_expires_at": None,
        "result_refs": {},
        "failure_summary": None,
        "retry_of_job_id": None,
    }
    values.update(overrides)
    return AgentJob.model_validate(values)


def make_agent_job_event(**overrides: object) -> AgentJobEvent:
    values: dict[str, object] = {
        "event_id": "agent-job-event-1",
        "job_id": "agent-job-1",
        "event_type": "queued",
        "message": "Queued artifact creation.",
        "created_at": MEMORY_NOW,
        "status": "queued",
        "public_visibility": True,
        "metadata": {"step": "queue"},
    }
    values.update(overrides)
    return AgentJobEvent.model_validate(values)


def make_agent_job_report(**overrides: object) -> AgentJobReport:
    values: dict[str, object] = {
        "report_id": "agent-job-report-1",
        "job_id": "agent-job-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "workspace_id": "project-1",
        "session_id": "session-1",
        "action_kind": "propose_memory_signal",
        "agent_label": "Memory Analyst",
        "status": "completed",
        "title": "Memory proposal pending review",
        "summary": "A memory proposal was created and is pending your review.",
        "public_resource_label": "Prefers C over Python",
        "created_at": MEMORY_NOW,
    }
    values.update(overrides)
    return AgentJobReport.model_validate(values)


def make_working_state_snapshot(**overrides) -> WorkingStateSnapshot:
    values = {
        "user_id": "user-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "source_message_id": "message-1",
        "request_summary": "Deployment plan with Cloud Run under consideration.",
        "current_goal": "Choose a deployment plan.",
        "intent_hypothesis": (
            "The user likely wants a secure deployment plan and is unsure "
            "whether background workers are necessary."
        ),
        "active_constraints": ("security matters more than speed",),
        "unresolved_questions": (),
        "clarification_status": "useful",
        "next_step_hypothesis": (
            "Prefer a synchronous MVP unless durability becomes required."
        ),
        "confidence": "medium",
        "updated_at": MEMORY_NOW,
    }
    values.update(overrides)
    return WorkingStateSnapshot(**values)


def make_continuity_choice() -> ContinuityChoice:
    return ContinuityChoice(
        choice_id="choice-0",
        source_kind="collaborative_note",
        source_id="note-export",
        display_label="Export workflow",
        match_reason="bounded_relevance",
    )


def make_alternate_continuity_choice() -> ContinuityChoice:
    return ContinuityChoice(
        choice_id="choice-1",
        source_kind="collaborative_note",
        source_id="note-export-constraints",
        display_label="Export constraints",
        match_reason="bounded_relevance",
    )


def make_chat_session_continuity_choice() -> ContinuityChoice:
    return ContinuityChoice(
        choice_id="choice-0",
        source_kind="chat_session",
        source_id="session-prior",
        display_label="Prior HIDS implementation discussion",
        match_reason="previous_chat",
    )


def make_alternate_chat_session_continuity_choice() -> ContinuityChoice:
    return ContinuityChoice(
        choice_id="choice-1",
        source_kind="chat_session",
        source_id="session-older",
        display_label="Older implementation discussion",
        match_reason="previous_chat",
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
    session_ownership_error_at: str | None = None
    history_calls: list[tuple[str, int | None, str, str, str | None]] = field(
        default_factory=list
    )
    save_calls: list[tuple[str, str, str, str, str]] = field(
        default_factory=list
    )
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
    chat_session_list_result: ChatSessionListResponse = field(
        default_factory=lambda: ChatSessionListResponse(sessions=[])
    )
    chat_session_detail_result: ChatSessionDetailResponse = field(
        default_factory=lambda: ChatSessionDetailResponse(
            session_id="session-1",
            project_id="project-1",
            user_id="user-1",
            messages=[],
        )
    )
    chat_session_error: Exception | None = None
    completed_model_message_text: str = "Canonical persisted answer."
    completed_model_message_error: Exception | None = None
    chat_session_list_calls: list[
        tuple[str, str, int]
    ] = field(default_factory=list)
    chat_session_detail_calls: list[
        tuple[str, str, str, int, datetime]
    ] = field(default_factory=list)
    completed_model_message_calls: list[
        tuple[str, str, str, str]
    ] = field(default_factory=list)
    workspace_list_result: WorkspaceListResponse = field(
        default_factory=lambda: WorkspaceListResponse(workspaces=[])
    )
    workspace_create_result: WorkspaceSummary = field(
        default_factory=lambda: WorkspaceSummary(
            workspace_id="agent-col",
            display_name="Agent Col",
            is_default=True,
        )
    )
    workspace_error: Exception | None = None
    workspace_list_calls: list[
        tuple[str, str, str, int]
    ] = field(default_factory=list)
    workspace_create_calls: list[
        tuple[str, str, WorkspaceCreateRequest]
    ] = field(default_factory=list)
    workspace_delete_calls: list[
        tuple[str, str, str, str]
    ] = field(default_factory=list)
    decision_action_calls: list[
        tuple[ChatTurnClaim, AgentActionReceipt, datetime]
    ] = field(default_factory=list)
    note_decision_effect_calls: list[
        tuple[ChatTurnClaim, CollaborativeNoteEvent, datetime]
    ] = field(default_factory=list)
    working_state: WorkingStateSnapshot | None = None
    working_state_error: Exception | None = None
    working_state_calls: list[tuple[str, str, str]] = field(
        default_factory=list
    )
    working_state_save_calls: list[
        tuple[WorkingStateSnapshot, datetime]
    ] = field(default_factory=list)
    closed: bool = False
    agent_job_repository: object | None = None

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
        user_id: str,
        project_id: str,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        self.history_calls.append(
            (
                session_id,
                limit,
                user_id,
                project_id,
                exclude_message_id,
            )
        )
        if self.session_ownership_error_at == "history":
            raise ChatSessionOwnershipError(
                "private-history-ownership-marker"
            )
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

    async def get_working_state(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
    ) -> WorkingStateSnapshot | None:
        self.working_state_calls.append((user_id, project_id, session_id))
        self.events.append(("working_state", session_id))
        if self.working_state_error is not None:
            raise self.working_state_error
        return self.working_state

    async def save_working_state(
        self,
        snapshot: WorkingStateSnapshot,
        *,
        observed_at: datetime,
    ) -> None:
        self.working_state_save_calls.append((snapshot, observed_at))
        self.events.append(("save_working_state", snapshot.session_id))
        if self.working_state_error is not None:
            raise self.working_state_error

    async def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        project_id: str,
        user_id: str,
    ) -> str:
        self.save_calls.append(
            (session_id, role, text, project_id, user_id)
        )
        if self.session_ownership_error_at == f"save_{role}":
            raise ChatSessionOwnershipError(
                f"private-{role}-save-ownership-marker"
            )
        if self.fail_on == f"save_{role}":
            raise main.MemoryEngineError(f"{role} save failed")
        self.events.append(("save", session_id, role, text))
        return f"{role}-message-1"

    async def list_chat_sessions(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int,
    ) -> ChatSessionListResponse:
        self.chat_session_list_calls.append((user_id, project_id, limit))
        self.events.append(("chat_session_list", user_id, project_id, limit))
        if self.chat_session_error is not None:
            raise self.chat_session_error
        return self.chat_session_list_result

    async def get_chat_session_detail(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
        observed_at: datetime,
    ) -> ChatSessionDetailResponse:
        self.chat_session_detail_calls.append(
            (user_id, project_id, session_id, limit, observed_at)
        )
        self.events.append(
            ("chat_session_detail", user_id, project_id, session_id, limit)
        )
        if self.chat_session_error is not None:
            raise self.chat_session_error
        return self.chat_session_detail_result

    async def get_completed_model_message(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        message_id: str,
    ) -> object:
        self.completed_model_message_calls.append(
            (user_id, project_id, session_id, message_id)
        )
        self.events.append(
            (
                "completed_model_message",
                user_id,
                project_id,
                session_id,
                message_id,
            )
        )
        if self.completed_model_message_error is not None:
            raise self.completed_model_message_error
        return SimpleNamespace(text=self.completed_model_message_text)

    async def list_workspaces(
        self,
        *,
        user_id: str,
        default_workspace_id: str,
        default_display_name: str,
        limit: int,
    ) -> WorkspaceListResponse:
        self.workspace_list_calls.append(
            (user_id, default_workspace_id, default_display_name, limit)
        )
        self.events.append(
            (
                "workspace_list",
                user_id,
                default_workspace_id,
                default_display_name,
                limit,
            )
        )
        if self.workspace_error is not None:
            raise self.workspace_error
        return self.workspace_list_result

    async def create_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: WorkspaceCreateRequest,
    ) -> WorkspaceSummary:
        self.workspace_create_calls.append((user_id, workspace_id, request))
        self.events.append(("workspace_create", user_id, workspace_id))
        if self.workspace_error is not None:
            raise self.workspace_error
        return self.workspace_create_result

    async def delete_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        default_workspace_id: str,
        default_display_name: str,
    ) -> None:
        self.workspace_delete_calls.append(
            (user_id, workspace_id, default_workspace_id, default_display_name)
        )
        self.events.append(("workspace_delete", user_id, workspace_id))
        if self.workspace_error is not None:
            raise self.workspace_error

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

    async def record_chat_turn_collaborative_note_decision_effect(
        self,
        claim: ChatTurnClaim,
        event: CollaborativeNoteEvent,
        *,
        observed_at: datetime,
    ) -> object:
        action = AgentActionReceipt(
            action_name=(
                "approve_collaborative_note"
                if claim.request.collaborative_note_decision is not None
                and claim.request.collaborative_note_decision.decision
                == "approve"
                else "reject_collaborative_note"
            ),
            status="completed",
        )
        refreshed = replace(
            claim,
            precompleted_actions=(*claim.precompleted_actions, action),
            precompleted_collaborative_note_events=(
                *claim.precompleted_collaborative_note_events,
                event,
            ),
        )
        self.note_decision_effect_calls.append((claim, event, observed_at))
        self.events.append(
            ("record_chat_turn_collaborative_note_decision_effect",)
        )
        return SimpleNamespace(
            claim=refreshed,
            action=action,
            event=event,
        )

    def close(self) -> None:
        self.closed = True

    def agent_jobs(self) -> object:
        if self.agent_job_repository is None:
            raise AssertionError("Missing fake agent job repository.")
        return self.agent_job_repository


@dataclass
class FakeAgentJobRepository:
    jobs: list[AgentJob] = field(
        default_factory=lambda: [make_agent_job()]
    )
    job_batches: list[list[AgentJob]] = field(default_factory=list)
    events: list[AgentJobEvent] = field(
        default_factory=lambda: [make_agent_job_event()]
    )
    reports: list[AgentJobReport] = field(
        default_factory=lambda: [make_agent_job_report()]
    )
    error: Exception | None = None
    list_calls: list[dict[str, object]] = field(default_factory=list)
    get_calls: list[dict[str, object]] = field(default_factory=list)
    event_calls: list[dict[str, object]] = field(default_factory=list)
    cancel_calls: list[dict[str, object]] = field(default_factory=list)
    retry_calls: list[dict[str, object]] = field(default_factory=list)

    async def list_jobs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ):
        self.list_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "session_id": session_id,
                "limit": limit,
            }
        )
        if self.error is not None:
            raise self.error
        jobs = self.jobs
        if self.job_batches:
            jobs = self.job_batches.pop(0)
        yielded = 0
        for job in jobs:
            if project_id is not None and job.project_id != project_id:
                continue
            if session_id is not None and job.session_id != session_id:
                continue
            yielded += 1
            if yielded > limit:
                return
            yield job

    async def list_reports(
        self,
        *,
        user_id: str,
        workspace_id: str,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ):
        self.list_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "session_id": session_id,
                "limit": limit,
                "kind": "reports",
            }
        )
        if self.error is not None:
            raise self.error
        yielded = 0
        for report in self.reports:
            if project_id is not None and report.project_id != project_id:
                continue
            if session_id is not None and report.session_id != session_id:
                continue
            yielded += 1
            if yielded > limit:
                return
            yield report

    async def get_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
    ) -> AgentJob:
        self.get_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
            }
        )
        if self.error is not None:
            raise self.error
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        raise AgentJobNotFoundError("missing fake job")

    async def list_events(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        limit: int = 50,
    ):
        self.event_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "limit": limit,
            }
        )
        if self.error is not None:
            raise self.error
        yielded = 0
        for event in self.events:
            if event.job_id != job_id:
                continue
            yielded += 1
            if yielded > limit:
                return
            yield event

    async def cancel_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        observed_at: datetime,
    ) -> AgentJob:
        self.cancel_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "observed_at": observed_at,
            }
        )
        if self.error is not None:
            raise self.error
        return make_agent_job(
            job_id=job_id,
            user_id=user_id,
            workspace_id=workspace_id,
            project_id=workspace_id,
            status="cancelled",
            updated_at=observed_at,
        )

    async def retry_job(
        self,
        *,
        user_id: str,
        workspace_id: str,
        source_job_id: str,
        retry_job_id: str,
        idempotency_key: str,
        observed_at: datetime,
    ) -> AgentJob:
        self.retry_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "source_job_id": source_job_id,
                "retry_job_id": retry_job_id,
                "idempotency_key": idempotency_key,
                "observed_at": observed_at,
            }
        )
        if self.error is not None:
            raise self.error
        return make_agent_job(
            job_id=retry_job_id,
            user_id=user_id,
            workspace_id=workspace_id,
            project_id=workspace_id,
            status="queued",
            created_at=observed_at,
            updated_at=observed_at,
            idempotency_key=idempotency_key,
            attempt_count=2,
            retry_of_job_id=source_job_id,
        )


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
class FakeSpeechTranscriptionService:
    events: list[tuple[Any, ...]]
    transcript: str = "recognized text"
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def transcribe(
        self,
        *,
        audio: bytes,
        content_type: str,
    ) -> str:
        self.calls.append({"audio": audio, "content_type": content_type})
        self.events.append(("speech_transcribe",))
        if self.error is not None:
            raise self.error
        return self.transcript


@dataclass
class FakeSpeechSynthesisService:
    events: list[tuple[Any, ...]]
    audio: bytes = b"mp3 audio bytes"
    content_type: str = "audio/mpeg"
    chunk_count: int = 1
    error: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def synthesize(
        self,
        *,
        text: str,
        chunk_index: int,
        voice_id: str = "female",
    ) -> object:
        self.calls.append(
            {
                "text": text,
                "chunk_index": chunk_index,
                "voice_id": voice_id,
            }
        )
        self.events.append(("speech_synthesize", chunk_index))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            audio=self.audio,
            content_type=self.content_type,
            chunk_index=chunk_index,
            chunk_count=self.chunk_count,
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
    stream_deltas: tuple[str, ...] = ("Generated ", "answer")
    stream_block_after_deltas: bool = False
    stream_cancelled: bool = False

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

    async def stream_turn(self, command: AgentColTurnCommand):
        self.calls.append(command)
        self.events.append(("turn_service",))
        for text in self.stream_deltas:
            self.events.append(("turn_delta", text))
            yield AgentColTextDelta(text=text)
        if self.stream_block_after_deltas:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.stream_cancelled = True
                raise
        if self.error is not None:
            raise self.error
        result = self.turn_result or AgentColTurnResult(
            response=self.response_text
        )
        yield AgentColTurnCompleted(result=result)


@dataclass
class FakeContinuityService:
    events: list[tuple[Any, ...]]
    resolution: ContinuityResolution = field(
        default_factory=lambda: ContinuityResolution(status="none")
    )
    error: Exception | None = None
    calls: list[ContinuityResolutionCommand] = field(default_factory=list)

    async def resolve(
        self,
        command: ContinuityResolutionCommand,
    ) -> ContinuityResolution:
        self.calls.append(command)
        self.events.append(("continuity_service",))
        if self.error is not None:
            raise self.error
        return self.resolution


@dataclass
class FakeWorkingStateService:
    events: list[tuple[Any, ...]]
    result: WorkingStateUpdateResult | None = None
    calls: list[WorkingStateUpdateInput] = field(default_factory=list)
    error: Exception | None = None

    async def update(
        self,
        command: WorkingStateUpdateInput,
    ) -> WorkingStateUpdateResult:
        self.calls.append(command)
        self.events.append(("working_state_service", command.session_id))
        if self.error is not None:
            raise self.error
        return self.result or WorkingStateUpdateResult(update_required=False)


@dataclass
class FakePreferenceLearningService:
    events: list[tuple[Any, ...]]
    result: object | None = None
    calls: list[object] = field(default_factory=list)
    error: Exception | None = None

    async def capture(self, command: object) -> object:
        self.calls.append(command)
        self.events.append(("preference_learning",))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        from preference_learning_service import PreferenceLearningResult

        return PreferenceLearningResult()


@dataclass
class FakeTrustedMemoryService:
    events: list[tuple[Any, ...]]
    result: TrustedMemoryInspectionResult
    error: Exception | None = None
    revoke_result: TrustedMemoryMutationResult | None = None
    delete_result: TrustedMemoryMutationResult | None = None
    decision_result: TrustedMemoryMutationResult | None = None
    natural_memory_result: (
        NaturalMemoryProposalResult | NaturalMemoryClarificationResult | None
    ) = None
    selection_result: NaturalMemoryProposalResult | None = None
    preference_confirmation_result: MemoryClarificationReceipt | None = None
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
    natural_memory_calls: list[NaturalMemoryCommand] = field(
        default_factory=list
    )
    selection_calls: list[SelectMemoryClarificationCommand] = field(
        default_factory=list
    )
    preference_confirmation_calls: list[dict[str, object]] = field(
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

    async def handle_natural_memory_decision(
        self,
        command: NaturalMemoryCommand,
    ) -> NaturalMemoryProposalResult | NaturalMemoryClarificationResult:
        self.natural_memory_calls.append(command)
        self.events.append(("natural_memory_decision",))
        if self.error is not None:
            raise self.error
        if self.natural_memory_result is None:
            raise AssertionError("Missing fake natural memory result.")
        return self.natural_memory_result

    async def select_memory_clarification(
        self,
        command: SelectMemoryClarificationCommand,
    ) -> NaturalMemoryProposalResult:
        self.selection_calls.append(command)
        self.events.append(("memory_clarification_selection",))
        if self.error is not None:
            raise self.error
        if self.selection_result is None:
            raise AssertionError("Missing fake clarification result.")
        return self.selection_result

    async def open_preference_hypothesis_confirmation(
        self,
        **kwargs: object,
    ) -> MemoryClarificationReceipt:
        self.preference_confirmation_calls.append(kwargs)
        self.events.append(("preference_confirmation",))
        if self.error is not None:
            raise self.error
        if self.preference_confirmation_result is None:
            raise AssertionError("Missing fake preference confirmation result.")
        return self.preference_confirmation_result

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
    record_result: RecordBlueprintFeedbackResult | None = None
    error: Exception | None = None
    calls: list[ListArtifactFeedbackCommand] = field(default_factory=list)
    record_calls: list[RecordBlueprintFeedbackCommand] = field(default_factory=list)

    async def list_feedback(
        self,
        command: ListArtifactFeedbackCommand,
    ) -> BlueprintArtifactFeedbackListResponse:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        return self.result

    async def record_feedback(
        self,
        command: RecordBlueprintFeedbackCommand,
    ) -> RecordBlueprintFeedbackResult:
        self.record_calls.append(command)
        if self.error is not None:
            raise self.error
        if self.record_result is None:
            raise AssertionError("Missing fake artifact feedback result.")
        return self.record_result


@dataclass
class FakeGenericArtifactReadService:
    events: list[tuple[Any, ...]]
    list_result: SingleFileArtifactListResponse
    detail_result: SingleFileArtifactDetailResponse
    list_error: Exception | None = None
    detail_error: Exception | None = None
    archive_error: Exception | None = None
    restore_error: Exception | None = None
    update_metadata_error: Exception | None = None
    create_version_error: Exception | None = None
    list_calls: list[ListGenericArtifactsCommand] = field(default_factory=list)
    detail_calls: list[GetGenericArtifactCommand] = field(default_factory=list)
    archive_calls: list[ArchiveGenericArtifactCommand] = (
        field(default_factory=list)
    )
    restore_calls: list[RestoreGenericArtifactCommand] = (
        field(default_factory=list)
    )
    update_metadata_calls: list[
        UpdateGenericArtifactMetadataCommand
    ] = field(default_factory=list)
    create_version_calls: list[
        CreateGenericArtifactVersionCommand
    ] = field(default_factory=list)
    delete_calls: list[DeleteGenericArtifactCommand] = field(
        default_factory=list
    )

    async def list_artifacts(
        self,
        command: ListGenericArtifactsCommand,
    ) -> SingleFileArtifactListResponse:
        self.list_calls.append(command)
        self.events.append(("generic_artifact_list",))
        if self.list_error is not None:
            raise self.list_error
        return self.list_result

    async def get_artifact(
        self,
        command: GetGenericArtifactCommand,
    ) -> SingleFileArtifactDetailResponse:
        self.detail_calls.append(command)
        self.events.append(("generic_artifact_detail",))
        if self.detail_error is not None:
            raise self.detail_error
        return self.detail_result

    async def archive_artifact(
        self,
        command: ArchiveGenericArtifactCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        self.archive_calls.append(command)
        self.events.append(("generic_artifact_archive",))
        if self.archive_error is not None:
            raise self.archive_error
        return SingleFileArtifactLifecycleResponse(
            metadata=self.detail_result.metadata.model_copy(
                update={"lifecycle_status": "archived"}
            )
        )

    async def restore_artifact(
        self,
        command: RestoreGenericArtifactCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        self.restore_calls.append(command)
        self.events.append(("generic_artifact_restore",))
        if self.restore_error is not None:
            raise self.restore_error
        return SingleFileArtifactLifecycleResponse(
            metadata=self.detail_result.metadata.model_copy(
                update={"lifecycle_status": "active"}
            )
        )

    async def update_artifact_metadata(
        self,
        command: UpdateGenericArtifactMetadataCommand,
    ) -> SingleFileArtifactLifecycleResponse:
        self.update_metadata_calls.append(command)
        self.events.append(("generic_artifact_update_metadata",))
        if self.update_metadata_error is not None:
            raise self.update_metadata_error
        return SingleFileArtifactLifecycleResponse(
            metadata=self.detail_result.metadata.model_copy(
                update={
                    "reference": (
                        self.detail_result.metadata.reference.model_copy(
                            update={"display_label": command.display_label}
                        )
                    ),
                    "filename": command.filename
                    or self.detail_result.metadata.filename,
                }
            )
        )

    async def create_artifact_version(
        self,
        command: CreateGenericArtifactVersionCommand,
    ) -> SingleFileArtifactCreateResponse:
        self.create_version_calls.append(command)
        self.events.append(("generic_artifact_create_version",))
        if self.create_version_error is not None:
            raise self.create_version_error
        artifact = self.detail_result.artifact.model_copy(
            update={
                "content": command.content,
                "filename": (
                    command.filename or self.detail_result.artifact.filename
                ),
                "summary": (
                    command.summary or self.detail_result.artifact.summary
                ),
            }
        )
        reference = self.detail_result.metadata.reference.model_copy(
            update={
                "artifact_id": "artifact-version-1",
                "display_label": (
                    command.display_label
                    or command.summary
                    or self.detail_result.metadata.reference.display_label
                ),
            }
        )
        return SingleFileArtifactCreateResponse(
            reference=reference,
            artifact=artifact,
        )

    async def delete_artifact(
        self,
        command: DeleteGenericArtifactCommand,
    ) -> None:
        self.delete_calls.append(command)
        self.events.append(("generic_artifact_delete",))


@dataclass
class FakeGenericArtifactGenerator:
    result: SingleFileArtifact
    error: Exception | None = None
    calls: list[tuple[object, GenericArtifactGenerationRequest]] = (
        field(default_factory=list)
    )

    async def __call__(
        self,
        client: object,
        artifact_request: GenericArtifactGenerationRequest,
    ) -> SingleFileArtifact:
        self.calls.append((client, artifact_request))
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class FakeGenericArtifactCreationService:
    result: GenericArtifactCreationResult
    error: Exception | None = None
    calls: list[GenericArtifactCreationCommand] = field(default_factory=list)

    async def create_artifact(
        self,
        command: GenericArtifactCreationCommand,
    ) -> GenericArtifactCreationResult:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        return self.result


def collaborative_note_payload(
    *, status: str = "active", revision: int = 1
) -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "project-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": status,
        "revision": revision,
        "source_session_id": "session-1",
        "source_message_ids": ["user-message-1"],
        "source_event_id": "event-1",
        "created_at": MEMORY_NOW,
        "updated_at": MEMORY_NOW,
    }


def collaborative_note_event_payload(
    event_type: str = "approved",
) -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "event_id": f"note-1--{event_type}--1",
        "note_id": "note-1",
        "proposal_id": "note-proposal-1",
        "owner_user_id": "user-1",
        "workspace_id": "project-1",
        "event_type": event_type,
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "source_session_id": "session-1",
        "source_message_ids": ["user-message-1"],
        "revision": 1,
        "previous_revision": None,
        "created_at": MEMORY_NOW,
    }


def collaborative_note_proposal_payload() -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "proposal_id": "note-proposal-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 3.",
        "source_session_id": "session-2",
        "source_message_ids": ["user-message-2"],
        "expected_note_id": "note-1",
        "expected_revision": 1,
        "policy_version": "1.0",
        "status": "pending",
        "created_at": MEMORY_NOW,
        "expires_at": MEMORY_NOW + timedelta(hours=24),
    }


@dataclass
class FakeCollaborativeNoteService:
    list_result: CollaborativeNoteListResult
    detail_result: CollaborativeNoteDetailResult
    proposal_result: CollaborativeNoteProposalResult
    lifecycle_result: CollaborativeNoteLifecycleResult
    deletion_result: CollaborativeNoteDeletionResult
    decision_result: CollaborativeNoteDecisionResult | None = None
    error: Exception | None = None
    list_calls: list[ListCollaborativeNotesCommand] = field(default_factory=list)
    detail_calls: list[GetCollaborativeNoteCommand] = field(default_factory=list)
    correction_calls: list[CollaborativeNoteCorrectionCommand] = field(
        default_factory=list
    )
    proposal_calls: list[CollaborativeNoteProposalCommand] = field(
        default_factory=list
    )
    decision_calls: list[CollaborativeNoteDecisionCommand] = field(
        default_factory=list
    )
    archive_calls: list[CollaborativeNoteLifecycleCommand] = field(
        default_factory=list
    )
    restore_calls: list[CollaborativeNoteLifecycleCommand] = field(
        default_factory=list
    )
    delete_calls: list[CollaborativeNoteLifecycleCommand] = field(
        default_factory=list
    )

    async def list_notes(
        self,
        command: ListCollaborativeNotesCommand,
    ) -> CollaborativeNoteListResult:
        self.list_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.list_result

    async def get_note(
        self,
        command: GetCollaborativeNoteCommand,
    ) -> CollaborativeNoteDetailResult:
        self.detail_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.detail_result

    async def create_correction(
        self,
        command: CollaborativeNoteCorrectionCommand,
    ) -> CollaborativeNoteProposalResult:
        self.correction_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.proposal_result

    async def create_proposal(
        self,
        command: CollaborativeNoteProposalCommand,
    ) -> CollaborativeNoteProposalResult:
        self.proposal_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.proposal_result

    async def decide_proposal(
        self,
        command: CollaborativeNoteDecisionCommand,
    ) -> CollaborativeNoteDecisionResult:
        self.decision_calls.append(command)
        if self.error is not None:
            raise self.error
        if self.decision_result is None:
            raise AssertionError("Missing fake note decision result.")
        return self.decision_result

    async def archive_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteLifecycleResult:
        self.archive_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.lifecycle_result

    async def restore_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteLifecycleResult:
        self.restore_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.lifecycle_result

    async def delete_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteDeletionResult:
        self.delete_calls.append(command)
        if self.error is not None:
            raise self.error
        return self.deletion_result


@dataclass
class ServiceState:
    events: list[tuple[Any, ...]]
    database: FakeMemoryEngine
    genai_client: FakeGenAIClient
    synthesis_service: FakeSynthesisApplicationService
    speech_transcription_service: FakeSpeechTranscriptionService
    speech_synthesis_service: FakeSpeechSynthesisService
    source_service: FakeSourceExpertService
    research_service: object
    computation_service: object
    requirements_verification_service: object
    expert_executor: object
    supervisor: FakeSupervisorRuntime
    turn_service: FakeAgentColTurnService
    continuity_service: FakeContinuityService
    working_state_service: FakeWorkingStateService
    preference_learning_service: FakePreferenceLearningService
    memory_service: FakeTrustedMemoryService
    collaborative_note_service: FakeCollaborativeNoteService
    artifact_service: FakeArtifactReadService
    generic_artifact_service: FakeGenericArtifactReadService
    artifact_executor: object
    artifact_feedback_service: FakeArtifactFeedbackService
    artifact_feedback_executor: object
    agent_job_repository: FakeAgentJobRepository
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
        tuple[object, object, object, object, object, object, object | None, object]
    ]
    artifact_feedback_service_dependencies: list[tuple[object, object]]
    artifact_feedback_executor_dependencies: list[tuple[object, object]]
    responder_note_services: list[object]
    responder_agent_job_repositories: list[object]
    continuity_service_dependencies: list[object]
    working_state_service_dependencies: list[object]
    preference_learning_service_dependencies: list[object]
    turn_service_dependencies: list[
        tuple[object, object, object, object, object]
    ]


@pytest.fixture
def service_state(monkeypatch: pytest.MonkeyPatch) -> ServiceState:
    events: list[tuple[Any, ...]] = []
    database = FakeMemoryEngine(events)
    agent_job_repository = FakeAgentJobRepository()
    database.agent_job_repository = agent_job_repository
    genai_client = FakeGenAIClient(FakeAsyncGenAI())
    blueprint = SynthesisBlueprint.model_validate(VALID_BLUEPRINT_PAYLOAD)
    synthesis_service = FakeSynthesisApplicationService(events, blueprint)
    speech_transcription_service = FakeSpeechTranscriptionService(events)
    speech_synthesis_service = FakeSpeechSynthesisService(events)
    source_service = FakeSourceExpertService(client=genai_client)
    research_service = object()
    computation_service = object()
    requirements_verification_service = object()
    expert_executor = object()
    responder_app = object()
    supervisor = FakeSupervisorRuntime(events)
    turn_service = FakeAgentColTurnService(events)
    continuity_service = FakeContinuityService(events)
    working_state_service = FakeWorkingStateService(events)
    preference_learning_service = FakePreferenceLearningService(events)
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
                    "policy_version": "1.0",
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
        selection_result=NaturalMemoryProposalResult(
            status="pending",
            action=AgentActionReceipt(
                action_name="propose_memory_signal",
                status="completed",
            ),
            proposal=MemoryProposalReceiptV2(
                proposal_id="response_length--clarified-proposal-1",
                category="response_length",
                proposed_value="detailed",
                expires_at=MEMORY_NOW + timedelta(hours=24),
            ),
        ),
    )
    note = CollaborativeNote.model_validate(collaborative_note_payload())
    note_event = CollaborativeNoteEvent.model_validate(
        collaborative_note_event_payload()
    )
    note_service = FakeCollaborativeNoteService(
        list_result=CollaborativeNoteListResult(
            notes=[note],
            next_note_id=None,
        ),
        detail_result=CollaborativeNoteDetailResult(
            note=note,
            events=[note_event],
        ),
        proposal_result=CollaborativeNoteProposalResult(
            proposal=CollaborativeNoteProposal.model_validate(
                collaborative_note_proposal_payload()
            )
        ),
        lifecycle_result=CollaborativeNoteLifecycleResult(
            note=note.model_copy(update={"status": "archived", "revision": 2}),
            event=CollaborativeNoteEvent.model_validate(
                {
                    **collaborative_note_event_payload("archived"),
                    "revision": 2,
                    "previous_revision": 1,
                }
            ),
        ),
        deletion_result=CollaborativeNoteDeletionResult(
            event=CollaborativeNoteEvent.model_validate(
                {
                    **collaborative_note_event_payload("deleted"),
                    "note_kind": None,
                    "title": None,
                    "body": None,
                    "source_session_id": None,
                    "source_message_ids": [],
                    "revision": 2,
                    "previous_revision": 1,
                }
            )
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
    generic_artifact = SingleFileArtifact(
        artifact_family="code",
        format="python",
        filename="password_generator.py",
        content="print('secure password placeholder')\n",
        summary="A simple Python password generator script.",
    )
    generic_artifact_metadata = SingleFileArtifactMetadata(
        reference=ArtifactReference(
            artifact_type="single_file_artifact",
            project_id="project-1",
            artifact_id="artifact-1",
            schema_version="1.0",
            display_label="Password Generator",
        ),
        created_at=MEMORY_NOW,
        originating_session_id="session-1",
        originating_turn_id="turn-1",
        filename="password_generator.py",
        artifact_family="code",
        format="python",
        byte_size=37,
    )
    generic_artifact_service = FakeGenericArtifactReadService(
        events=events,
        list_result=SingleFileArtifactListResponse(
            artifacts=[generic_artifact_metadata],
            next_before=None,
        ),
        detail_result=SingleFileArtifactDetailResponse(
            metadata=generic_artifact_metadata,
            artifact=generic_artifact,
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
        tuple[object, object, object, object, object, object, object | None, object]
    ] = []
    artifact_feedback_service_dependencies: list[tuple[object, object]] = []
    artifact_feedback_executor_dependencies: list[tuple[object, object]] = []
    responder_note_services: list[object] = []
    responder_agent_job_repositories: list[object] = []
    continuity_service_dependencies: list[object] = []
    working_state_service_dependencies: list[object] = []
    preference_learning_service_dependencies: list[object] = []
    turn_service_dependencies: list[
        tuple[object, object, object, object, object]
    ] = []
    state = ServiceState(
        events=events,
        database=database,
        genai_client=genai_client,
        synthesis_service=synthesis_service,
        speech_transcription_service=speech_transcription_service,
        speech_synthesis_service=speech_synthesis_service,
        source_service=source_service,
        research_service=research_service,
        computation_service=computation_service,
        requirements_verification_service=(
            requirements_verification_service
        ),
        expert_executor=expert_executor,
        supervisor=supervisor,
        turn_service=turn_service,
        continuity_service=continuity_service,
        working_state_service=working_state_service,
        preference_learning_service=preference_learning_service,
        memory_service=memory_service,
        collaborative_note_service=note_service,
        artifact_service=artifact_service,
        generic_artifact_service=generic_artifact_service,
        artifact_executor=artifact_executor,
        artifact_feedback_service=artifact_feedback_service,
        artifact_feedback_executor=artifact_feedback_executor,
        agent_job_repository=agent_job_repository,
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
        responder_note_services=responder_note_services,
        responder_agent_job_repositories=responder_agent_job_repositories,
        continuity_service_dependencies=continuity_service_dependencies,
        working_state_service_dependencies=(
            working_state_service_dependencies
        ),
        preference_learning_service_dependencies=(
            preference_learning_service_dependencies
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
    monkeypatch.setattr(
        main,
        "CloudSpeechTranscriptionService",
        lambda: speech_transcription_service,
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "CloudTextToSpeechSynthesisService",
        lambda: speech_synthesis_service,
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
        collaborative_note_service: object | None = None,
        agent_job_repository: object | None = None,
        memory_job_dispatcher: object | None = None,
    ) -> object:
        responder_vertex_settings.append(vertex_settings)
        responder_memory_services.append(memory_service)
        responder_note_services.append(collaborative_note_service)
        responder_agent_job_repositories.append(agent_job_repository)
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
        "CollaborativeNoteService",
        lambda *, database: (
            note_service
            if database is state.database
            else pytest.fail("Unexpected note service database.")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "GeminiContinuityTermExpander",
        lambda *, client: (
            object()
            if client is state.genai_client
            else pytest.fail("Unexpected continuity term-expander client.")
        ),
        raising=False,
    )
    def create_continuity_service(
        *,
        store: object,
        term_expander: object | None = None,
    ) -> object:
        continuity_service_dependencies.extend([store, term_expander])
        if store is not state.database:
            pytest.fail("Unexpected continuity store.")
        if term_expander is None:
            pytest.fail("Missing continuity term expander.")
        return continuity_service

    monkeypatch.setattr(
        main,
        "ContinuityService",
        create_continuity_service,
        raising=False,
    )

    def create_working_state_service(*, client: object) -> object:
        working_state_service_dependencies.append(client)
        if client is not state.genai_client:
            pytest.fail("Unexpected working-state service client.")
        return working_state_service

    monkeypatch.setattr(
        main,
        "WorkingStateService",
        create_working_state_service,
        raising=False,
    )

    def create_preference_learning_service(
        *,
        database: object,
        clock: object,
    ) -> object:
        preference_learning_service_dependencies.extend([database, clock])
        if database is not state.database:
            pytest.fail("Unexpected preference learning database.")
        return preference_learning_service

    monkeypatch.setattr(
        main,
        "PreferenceLearningService",
        create_preference_learning_service,
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
    monkeypatch.setattr(
        main,
        "GenericArtifactReadService",
        lambda *, database: (
            generic_artifact_service
            if database is state.database
            else pytest.fail("Unexpected generic artifact service database.")
        ),
        raising=False,
    )

    def create_artifact_executor(
        *,
        synthesis_service: object,
        artifact_ledger: object,
        artifact_reader: object,
        generic_artifact_generator: object,
        generic_artifact_reader: object,
        genai_client: object,
        agent_job_repository: object | None = None,
        artifact_job_dispatcher: object | None = None,
    ) -> object:
        artifact_executor_dependencies.append(
            (
                synthesis_service,
                artifact_ledger,
                artifact_reader,
                generic_artifact_generator,
                generic_artifact_reader,
                genai_client,
                agent_job_repository,
                artifact_job_dispatcher,
            )
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


def parse_sse_events(body: str) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        fields = {
            key: value.lstrip()
            for key, value in (
                line.split(":", 1)
                for line in frame.splitlines()
                if ":" in line
            )
        }
        events.append((fields["event"], json.loads(fields["data"])))
    return events


async def wait_for_working_state_background_tasks() -> None:
    tasks = getattr(main.app.state, "working_state_background_tasks", set())
    if tasks:
        await asyncio.gather(*tuple(tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "online"}


@pytest.mark.asyncio
async def test_chat_stream_emits_deltas_then_canonical_final(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse_events(response.text)
    assert events[:2] == [
        ("delta", {"text": "Generated "}),
        ("delta", {"text": "answer"}),
    ]
    assert events[2][0] == "final"
    assert events[2][1] == ChatResponse(
        response="Generated answer",
        actions=[],
        artifacts=[],
        citations=[],
        adaptations=[],
    ).model_dump(mode="json")
    assert service_state.database.complete_calls


@pytest.mark.asyncio
async def test_chat_stream_waits_for_persistence_before_final(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    persistence_started = asyncio.Event()
    allow_persistence = asyncio.Event()
    complete_chat_turn = service_state.database.complete_chat_turn

    async def blocked_complete_chat_turn(*args: object, **kwargs: object):
        persistence_started.set()
        await allow_persistence.wait()
        return await complete_chat_turn(*args, **kwargs)

    monkeypatch.setattr(
        service_state.database,
        "complete_chat_turn",
        blocked_complete_chat_turn,
    )
    request = main.Request(
        {
            "type": "http",
            "app": main.app,
            "method": "POST",
            "path": "/api/chat/stream",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )
    response = await main.chat_stream(
        main.ChatRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="New question",
        ),
        request,
        "owned-key-1",
        None,
    )
    iterator = response.body_iterator

    first_delta = await anext(iterator)
    second_delta = await anext(iterator)
    await persistence_started.wait()
    pending_final = asyncio.create_task(anext(iterator))
    await asyncio.sleep(0)

    assert parse_sse_events(str(first_delta)) == [
        ("delta", {"text": "Generated "})
    ]
    assert parse_sse_events(str(second_delta)) == [
        ("delta", {"text": "answer"})
    ]
    assert not pending_final.done()

    allow_persistence.set()
    final_frame = await pending_final
    assert parse_sse_events(str(final_frame))[0][0] == "final"
    assert service_state.database.complete_calls
    await iterator.aclose()


@pytest.mark.asyncio
async def test_chat_stream_emits_error_without_final_when_persistence_fails(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.database.complete_error = main.MemoryEngineError(
        "private persistence failure"
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    events = parse_sse_events(response.text)
    assert [event for event, _ in events] == ["delta", "delta", "error"]
    assert events[-1][1] == {
        "detail": "Database operation failed.",
        "status": 500,
        "provisional": True,
    }
    assert service_state.working_state_service.calls == []
    assert "private persistence failure" not in response.text


@pytest.mark.asyncio
async def test_chat_stream_emits_final_after_working_state_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    message = (
        "I want a deployment plan, probably Cloud Run, but security "
        "matters more than speed."
    )
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = replace(
        claim,
        request=replace(claim.request, message=message),
    )
    service_state.working_state_service.error = main.WorkingStateGenerationError(
        "private working state failure"
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": message,
        },
    )

    events = parse_sse_events(response.text)
    assert [event for event, _ in events] == ["delta", "delta", "final"]
    assert service_state.database.complete_calls
    assert len(service_state.working_state_service.calls) == 1
    assert "private working state failure" not in response.text


@pytest.mark.asyncio
async def test_chat_stream_replay_emits_canonical_final_only(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    stored_response = ChatResponse(
        response="Stored answer",
        actions=[],
        artifacts=[],
        citations=[],
        adaptations=[],
    )
    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "replay-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert parse_sse_events(response.text) == [
        ("final", stored_response.model_dump(mode="json"))
    ]
    assert service_state.turn_service.calls == []
    assert service_state.database.complete_calls == []


@pytest.mark.asyncio
async def test_chat_stream_preserves_live_idempotency_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_error = ChatTurnInProgressError(17)

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "live-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Chat turn is already in progress."}
    assert response.headers["retry-after"] == "17"
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_stream_requires_structured_decisions_to_use_json_endpoint(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "decision-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Yes, remember that preference.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Structured chat decisions must use /api/chat."
    }
    assert service_state.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "user_id", "project_id", "expected_status"),
    (
        (None, public_user_locator("109876543210"), "project-1", 401),
        (
            "Bearer token-abc",
            public_user_locator("999999999999"),
            google_subject_to_workspace_project_id("999999999999"),
            403,
        ),
    ),
)
async def test_structured_chat_stream_checks_google_ownership_before_eligibility(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    authorization: str | None,
    user_id: str,
    project_id: str,
    expected_status: int,
) -> None:
    subject = "109876543210"
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    headers = {"Idempotency-Key": "decision-key-1"}
    if authorization is not None:
        headers["Authorization"] = authorization

    response = await client.post(
        "/api/chat/stream",
        headers=headers,
        json={
            "project_id": project_id,
            "session_id": "session-1",
            "user_id": user_id,
            "message": "Yes, remember that preference.",
            "memory_decision": {
                "proposal_id": "response_length--proposal-1",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == expected_status
    assert service_state.events == []
    assert service_state.database.claim_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_google_chat_stream_uses_verified_owner_through_completion(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id=project_id,
                display_name="Private Google workspace",
                is_default=True,
            )
        ]
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.database.chat_turn_result = make_chat_turn_claim()

    response = await client.post(
        "/api/chat/stream",
        headers={
            "Authorization": "Bearer token-abc",
            "Idempotency-Key": "google-stream-key-1",
        },
        json={
            "project_id": project_id,
            "session_id": "google-session-1",
            "user_id": public_user_id,
            "message": "New question",
        },
    )

    events = parse_sse_events(response.text)
    assert response.status_code == 200
    assert events[-1][0] == "final"
    assert service_state.database.claim_calls[0][0].user_id == user_id
    assert service_state.database.claim_calls[0][0].project_id == project_id
    assert service_state.turn_service.calls[0].user_id == user_id
    assert service_state.turn_service.calls[0].project_id == project_id
    assert service_state.database.complete_calls


@pytest.mark.asyncio
async def test_google_chat_rejects_owned_but_hidden_workspace_before_claim(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    deleted_default_project_id = google_subject_to_workspace_project_id(
        subject
    )
    visible_project_id = f"{deleted_default_project_id}--study-plans"
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id=visible_project_id,
                display_name="Study Plans",
                is_default=False,
            )
        ]
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )

    response = await client.post(
        "/api/chat",
        headers={
            "Authorization": "Bearer token-abc",
            "Idempotency-Key": "hidden-workspace-key-1",
        },
        json={
            "project_id": deleted_default_project_id,
            "session_id": "google-session-1",
            "user_id": public_user_id,
            "message": "New question",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace is unavailable."}
    assert service_state.database.workspace_list_calls == [
        (
            user_id,
            deleted_default_project_id,
            "Private Google workspace",
            50,
        )
    ]
    assert service_state.database.claim_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_google_chat_rejects_when_no_visible_workspaces_before_claim(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    default_project_id = google_subject_to_workspace_project_id(subject)
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[]
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )

    response = await client.post(
        "/api/chat",
        headers={
            "Authorization": "Bearer token-abc",
            "Idempotency-Key": "no-visible-workspace-key-1",
        },
        json={
            "project_id": default_project_id,
            "session_id": "google-session-1",
            "user_id": public_user_id,
            "message": "New question",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace is unavailable."}
    assert service_state.database.workspace_list_calls == [
        (
            user_id,
            default_project_id,
            "Private Google workspace",
            50,
        )
    ]
    assert service_state.database.claim_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deltas", "provisional"),
    (((), False), (("Provisional text",), True)),
)
async def test_chat_stream_sanitizes_responder_failure_before_or_after_deltas(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    deltas: tuple[str, ...],
    provisional: bool,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.turn_service.stream_deltas = deltas
    service_state.turn_service.error = AgentColTurnResponderError(
        "private provider failure"
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    events = parse_sse_events(response.text)
    assert events[-1] == (
        "error",
        {
            "detail": "Agent_Col response failed.",
            "status": 502,
            "provisional": provisional,
        },
    )
    assert "final" not in [event for event, _ in events]
    assert "private provider failure" not in response.text
    assert len(service_state.database.release_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deltas", "provisional"),
    (((), False), (("Provisional text",), True)),
)
async def test_chat_stream_reports_timeout_before_or_after_deltas(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    deltas: tuple[str, ...],
    provisional: bool,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.turn_service.stream_deltas = deltas
    service_state.turn_service.error = AgentColTurnTimeoutError(
        "private timeout failure"
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "timeout-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    events = parse_sse_events(response.text)
    assert events[-1] == (
        "error",
        {
            "detail": "Agent_Col response timed out.",
            "status": 504,
            "provisional": provisional,
        },
    )
    assert "final" not in [event for event, _ in events]
    assert "private timeout failure" not in response.text
    assert len(service_state.database.release_calls) == 1


@pytest.mark.asyncio
async def test_chat_stream_preserves_structured_partial_failure_effects(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    action = AgentActionReceipt(
        action_name="propose_memory_signal",
        status="completed",
    )
    proposal = make_memory_proposal_receipt()
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.turn_service.stream_deltas = ("Provisional text",)
    service_state.turn_service.error = AgentColTurnResponderError(
        "private responder failure",
        actions=(action,),
        memory_proposals=(proposal,),
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "partial-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Remember this preference.",
        },
    )

    events = parse_sse_events(response.text)
    error = events[-1][1]
    assert events[-1][0] == "error"
    assert error["status"] == 502
    assert error["provisional"] is True
    assert error["partial_failure"] == {
        "detail": "Agent_Col response failed after a completed action.",
        "actions": [action.model_dump(mode="json")],
        "memory_proposals": [proposal.model_dump(mode="json")],
    }
    assert "final" not in [event for event, _ in events]


@pytest.mark.asyncio
async def test_chat_stream_preserves_queued_action_partial_failure_effects(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    queued_action = QueuedActionReceipt(
        job_id="memory-job-1",
        action_kind="propose_memory_signal",
        status="queued",
        display_label="Memory request: response_length",
        created_at=MEMORY_NOW,
        agent_label="Memory Analyst",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.turn_service.stream_deltas = ("Provisional text",)
    service_state.turn_service.error = AgentColTurnResponderError(
        "private responder failure",
        queued_actions=(queued_action,),
    )

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "queued-partial-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Remember this preference.",
        },
    )

    events = parse_sse_events(response.text)
    error = events[-1][1]
    assert events[-1][0] == "error"
    assert error["status"] == 502
    assert error["provisional"] is True
    assert error["partial_failure"] == {
        "detail": "Agent_Col response failed after a completed action.",
        "actions": [],
        "memory_proposals": [],
        "queued_actions": [queued_action.model_dump(mode="json")],
    }
    assert "final" not in [event for event, _ in events]


@pytest.mark.asyncio
async def test_chat_stream_disconnect_cancels_responder_without_completing_claim(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    service_state.turn_service.stream_deltas = ("Provisional text",)
    service_state.turn_service.stream_block_after_deltas = True
    request = main.Request(
        {
            "type": "http",
            "app": main.app,
            "method": "POST",
            "path": "/api/chat/stream",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )
    response = await main.chat_stream(
        main.ChatRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message="New question",
        ),
        request,
        "owned-key-1",
        None,
    )
    first_body_sent = asyncio.Event()
    sent_messages: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_body_sent.set()

    async def receive() -> dict[str, object]:
        await first_body_sent.wait()
        return {"type": "http.disconnect"}

    await asyncio.wait_for(
        response(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
            },
            receive,
            send,
        ),
        timeout=1.0,
    )

    assert service_state.turn_service.stream_cancelled is True
    assert service_state.database.complete_calls == []
    assert service_state.database.release_calls == []
    bodies = [
        bytes(message.get("body", b"")).decode()
        for message in sent_messages
        if message["type"] == "http.response.body" and message.get("body")
    ]
    assert [event for body in bodies for event, _ in parse_sse_events(body)] == [
        "delta"
    ]


@pytest.mark.asyncio
async def test_chat_stream_emits_final_before_slow_working_state_update(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = (
        "I want a deployment plan, probably Cloud Run, but security "
        "matters more than speed."
    )
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = replace(
        claim,
        request=replace(claim.request, message=message),
    )
    maintenance_started = asyncio.Event()
    unblock_maintenance = asyncio.Event()
    final_sent = asyncio.Event()

    async def blocked_update(command: WorkingStateUpdateInput):
        service_state.working_state_service.calls.append(command)
        maintenance_started.set()
        await unblock_maintenance.wait()
        return WorkingStateUpdateResult(update_required=False)

    monkeypatch.setattr(
        service_state.working_state_service,
        "update",
        blocked_update,
    )
    request = main.Request(
        {
            "type": "http",
            "app": main.app,
            "method": "POST",
            "path": "/api/chat/stream",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )
    response = await main.chat_stream(
        main.ChatRequest(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            message=message,
        ),
        request,
        "persisted-disconnect-key-1",
        None,
    )
    sent_messages: list[dict[str, object]] = []

    async def send(event: dict[str, object]) -> None:
        sent_messages.append(event)
        body = bytes(event.get("body", b"")).decode()
        if '"event": "final"' in body or "event: final" in body:
            final_sent.set()

    async def receive() -> dict[str, object]:
        await final_sent.wait()
        return {"type": "http.disconnect"}

    try:
        await asyncio.wait_for(
            response(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                },
                receive,
                send,
            ),
            timeout=1.0,
        )
    finally:
        unblock_maintenance.set()
        await wait_for_working_state_background_tasks()

    assert len(service_state.database.complete_calls) == 1
    assert service_state.database.release_calls == []
    bodies = [
        bytes(event.get("body", b"")).decode()
        for event in sent_messages
        if event["type"] == "http.response.body" and event.get("body")
    ]
    assert [
        event for body in bodies for event, _ in parse_sse_events(body)
    ] == ["delta", "delta", "final"]

    stored_response = service_state.database.complete_calls[0][1]
    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )
    replay = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "persisted-disconnect-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": message,
        },
    )

    assert parse_sse_events(replay.text) == [
        ("final", stored_response.model_dump(mode="json"))
    ]


@pytest.mark.asyncio
async def test_chat_json_returns_before_slow_working_state_update(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = (
        "I want a deployment plan, probably Cloud Run, but security "
        "matters more than speed."
    )
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = replace(
        claim,
        request=replace(claim.request, message=message),
    )
    maintenance_started = asyncio.Event()
    unblock_maintenance = asyncio.Event()

    async def blocked_update(command: WorkingStateUpdateInput):
        service_state.working_state_service.calls.append(command)
        maintenance_started.set()
        await unblock_maintenance.wait()
        return WorkingStateUpdateResult(update_required=False)

    monkeypatch.setattr(
        service_state.working_state_service,
        "update",
        blocked_update,
    )

    request_task = asyncio.create_task(
        client.post(
            "/api/chat",
            headers={"Idempotency-Key": "slow-maintenance-key-1"},
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": message,
            },
        )
    )

    try:
        response = await asyncio.wait_for(request_task, timeout=1.0)
        await asyncio.wait_for(maintenance_started.wait(), timeout=1.0)
    finally:
        unblock_maintenance.set()
        await wait_for_working_state_background_tasks()
        if not request_task.done():
            request_task.cancel()
            with suppress(asyncio.CancelledError):
                await request_task

    assert response.status_code == 200
    assert response.json()["response"] == "Generated answer"
    assert len(service_state.database.complete_calls) == 1
    assert len(service_state.working_state_service.calls) == 1


@pytest.mark.asyncio
async def test_chat_background_working_state_unexpected_failure_is_logged(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = (
        "I want a deployment plan, probably Cloud Run, but security "
        "matters more than speed."
    )
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = replace(
        claim,
        request=replace(claim.request, message=message),
    )

    async def unexpected_failure(command: WorkingStateUpdateInput):
        service_state.working_state_service.calls.append(command)
        raise RuntimeError("private unexpected working-state marker")

    monkeypatch.setattr(
        service_state.working_state_service,
        "update",
        unexpected_failure,
    )

    with caplog.at_level(logging.ERROR):
        response = await client.post(
            "/api/chat",
            headers={"Idempotency-Key": "unexpected-maintenance-key-1"},
            json={
                "project_id": "project-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "message": message,
            },
        )
        await wait_for_working_state_background_tasks()

    assert response.status_code == 200
    assert response.json()["response"] == "Generated answer"
    assert len(service_state.working_state_service.calls) == 1
    assert "Hidden working state update failed unexpectedly (RuntimeError)." in (
        caplog.text
    )
    assert "private unexpected working-state marker" not in response.text
    assert "private unexpected working-state marker" not in caplog.text


@pytest.mark.asyncio
async def test_oversized_raw_body_is_rejected_before_json_parsing(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    oversized_invalid_json = b"{" + (
        b"x" * (main.MAX_REQUEST_BODY_BYTES + 1)
    )

    response = await client.post(
        "/api/chat",
        content=oversized_invalid_json,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large."}
    assert service_state.events == []


@pytest.mark.asyncio
async def test_streamed_oversized_raw_body_is_rejected_before_json_parsing(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    async def oversized_stream():
        yield b"{"
        yield b"x" * (main.MAX_REQUEST_BODY_BYTES + 1)

    response = await client.post(
        "/api/chat",
        content=oversized_stream(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large."}
    assert service_state.events == []


@pytest.mark.asyncio
async def test_speech_transcribe_allows_body_above_default_api_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    audio_body = b"x" * (main.MAX_REQUEST_BODY_BYTES + 1)

    response = await client.post(
        "/api/speech/transcribe",
        content=audio_body,
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "recognized text"}
    assert service_state.speech_transcription_service.calls == [
        {
            "audio": audio_body,
            "content_type": "audio/webm;codecs=opus",
        }
    ]
    assert service_state.events == [("speech_transcribe",)]


@pytest.mark.asyncio
async def test_speech_transcribe_uses_configured_speech_body_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_COL_SPEECH_MAX_AUDIO_BYTES", "1024")

    response = await client.post(
        "/api/speech/transcribe",
        content=b"x" * 1025,
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large."}
    assert service_state.events == []
    assert service_state.speech_transcription_service.calls == []


@pytest.mark.asyncio
async def test_speech_transcribe_requires_google_authentication(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.post(
        "/api/speech/transcribe",
        content=b"webm audio",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authorization bearer token is required."
    }
    assert service_state.events == []
    assert service_state.speech_transcription_service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    (
        "audio/webm",
        "audio/webm;codecs=opus",
        "audio/webm; codecs=opus",
    ),
)
async def test_speech_transcribe_accepts_supported_webm_audio(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    content_type: str,
) -> None:
    audio_body = b"webm opus audio"

    response = await client.post(
        "/api/speech/transcribe",
        headers={
            "Authorization": "Bearer token-abc",
            "Content-Type": content_type,
        },
        content=audio_body,
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "recognized text"}
    assert service_state.speech_transcription_service.calls == [
        {
            "audio": audio_body,
            "content_type": "audio/webm"
            if content_type == "audio/webm"
            else "audio/webm;codecs=opus",
        }
    ]
    assert service_state.database.claim_calls == []
    assert service_state.database.save_calls == []
    assert service_state.database.complete_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_speech_transcribe_rejects_unsupported_mime(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/speech/transcribe",
        content=b"not allowed",
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "Unsupported audio content type."}
    assert service_state.events == []
    assert service_state.speech_transcription_service.calls == []


@pytest.mark.asyncio
async def test_speech_transcribe_returns_transcript_only(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.speech_transcription_service.transcript = "draft transcript"

    response = await client.post(
        "/api/speech/transcribe",
        content=b"webm audio",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "draft transcript"}


@pytest.mark.asyncio
async def test_speech_transcribe_rejects_empty_audio_before_provider(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/speech/transcribe",
        content=b"",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Speech audio is required."}
    assert service_state.events == []
    assert service_state.speech_transcription_service.calls == []


@pytest.mark.asyncio
async def test_speech_transcribe_sanitizes_provider_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.speech_transcription_service.error = RuntimeError(
        "private credential path /secret/project"
    )

    response = await client.post(
        "/api/speech/transcribe",
        content=b"webm audio",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Speech transcription failed."}
    assert "private credential" not in response.text


@pytest.mark.asyncio
async def test_speech_transcribe_logs_provider_cause_without_leaking_it_to_client(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider_error = SpeechTranscriptionProviderError(
        "private wrapped transcription error"
    )
    provider_error.__cause__ = RuntimeError(
        "private credential path /secret/project"
    )
    service_state.speech_transcription_service.error = provider_error
    caplog.set_level(logging.ERROR, logger=main.logger.name)

    response = await client.post(
        "/api/speech/transcribe",
        content=b"webm audio",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Speech transcription failed."}
    assert "provider_error=SpeechTranscriptionProviderError" in caplog.text
    assert "provider_cause=RuntimeError" in caplog.text
    assert "private credential" not in response.text
    assert "private credential" not in caplog.text
    assert "private wrapped" not in caplog.text


@pytest.mark.asyncio
async def test_speech_synthesize_returns_canonical_audio_bytes(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    message_id = "turn--aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa--model"

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": message_id,
            "chunk_index": 0,
        },
    )

    assert response.status_code == 200
    assert response.content == b"mp3 audio bytes"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["x-speech-chunk-index"] == "0"
    assert response.headers["x-speech-chunk-count"] == "1"
    assert service_state.database.completed_model_message_calls == [
        ("user-1", "project-1", "session-1", message_id)
    ]
    assert service_state.speech_synthesis_service.calls == [
        {
            "text": "Canonical persisted answer.",
            "chunk_index": 0,
            "voice_id": "female",
        }
    ]
    assert service_state.speech_transcription_service.calls == []
    assert service_state.database.claim_calls == []
    assert service_state.database.save_calls == []
    assert service_state.database.complete_calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_rejects_browser_supplied_text(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
            "text": "Browser replacement text",
        },
    )

    assert response.status_code == 422
    assert service_state.database.completed_model_message_calls == []
    assert service_state.speech_synthesis_service.calls == []
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_uses_approved_male_voice_id(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
            "voice_id": "male",
        },
    )

    assert response.status_code == 200
    assert service_state.speech_synthesis_service.calls == [
        {
            "text": "Canonical persisted answer.",
            "chunk_index": 0,
            "voice_id": "male",
        }
    ]


@pytest.mark.asyncio
async def test_speech_synthesize_rejects_raw_google_voice_name(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
            "voice_id": "en-GB-Chirp3-HD-Alnilam",
        },
    )

    assert response.status_code == 422
    assert service_state.database.completed_model_message_calls == []
    assert service_state.speech_synthesis_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_requires_google_authentication(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authorization bearer token is required."
    }
    assert service_state.database.completed_model_message_calls == []
    assert service_state.speech_synthesis_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_uses_verified_google_owner(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    message_id = "turn--aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa--model"
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )

    response = await client.post(
        f"/api/users/{public_user_id}/speech/synthesize",
        headers={"Authorization": "Bearer token-abc"},
        json={
            "project_id": project_id,
            "session_id": "google-session-1",
            "message_id": message_id,
        },
    )

    assert response.status_code == 200
    assert service_state.database.completed_model_message_calls == [
        (
            f"google--{subject}",
            project_id,
            "google-session-1",
            message_id,
        )
    ]


@pytest.mark.asyncio
async def test_speech_synthesize_rejects_unowned_message(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.completed_model_message_error = (
        ChatSessionOwnershipError("private ownership marker")
    )

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Speech message was not found."}
    assert "private ownership" not in response.text
    assert service_state.speech_synthesis_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_rejects_non_completed_model_message(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.completed_model_message_error = ChatTurnStateError(
        "private state marker"
    )

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "turn--aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa--user",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Speech requires a completed model message."
    }
    assert "private state" not in response.text
    assert service_state.speech_synthesis_service.calls == []


@pytest.mark.asyncio
async def test_speech_synthesize_rejects_unavailable_chunk(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.speech_synthesis_service.error = SpeechSynthesisChunkError(
        "private chunk marker"
    )

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
            "chunk_index": 3,
        },
    )

    assert response.status_code == 416
    assert response.json() == {"detail": "Speech chunk was not found."}
    assert "private chunk" not in response.text


@pytest.mark.asyncio
async def test_speech_synthesize_sanitizes_provider_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.speech_synthesis_service.error = SpeechSynthesisProviderError(
        "private provider path"
    )

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Speech synthesis failed."}
    assert "private provider" not in response.text


@pytest.mark.asyncio
async def test_speech_synthesize_logs_provider_cause_without_leaking_it_to_client(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider_error = SpeechSynthesisProviderError(
        "private wrapped synthesis error"
    )
    provider_error.__cause__ = RuntimeError(
        "private tts provider path /secret/project"
    )
    service_state.speech_synthesis_service.error = provider_error
    caplog.set_level(logging.ERROR, logger=main.logger.name)

    response = await client.post(
        "/api/users/user-1/speech/synthesize",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "message_id": "message-1",
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Speech synthesis failed."}
    assert "provider_error=SpeechSynthesisProviderError" in caplog.text
    assert "provider_cause=RuntimeError" in caplog.text
    assert "private tts" not in response.text
    assert "private tts" not in caplog.text
    assert "private wrapped" not in caplog.text


@pytest.mark.asyncio
async def test_schema_chat_limit_remains_distinct_from_raw_body_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    too_long_message = "x" * 10_001

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": too_long_message,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "message"]
    assert service_state.events == []


@pytest.mark.asyncio
async def test_scoped_rate_limiter_returns_retry_after_for_expensive_routes(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    main.app.state.rate_limiter = main.InMemoryRateLimiter(
        max_requests=1,
        window_seconds=30,
        clock=lambda: 100.0,
    )
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "What should I work on next?",
    }

    first_response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "rate-limit-chat-key-1"},
        json=payload,
    )
    second_response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "rate-limit-chat-key-2"},
        json=payload,
    )
    health_response = await client.get("/")
    workspace_response = await client.get("/workspace")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "30"
    assert second_response.json() == {"detail": "Rate limit exceeded."}
    assert health_response.status_code == 200
    assert workspace_response.status_code == 200
    assert service_state.events.count(("claim_chat_turn",)) == 1


@pytest.mark.asyncio
async def test_scoped_rate_limiter_covers_streaming_chat(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    main.app.state.rate_limiter = main.InMemoryRateLimiter(
        max_requests=1,
        window_seconds=30,
        clock=lambda: 100.0,
    )
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "What should I work on next?",
    }

    first_response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "rate-limit-stream-key-1"},
        json=payload,
    )
    second_response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "rate-limit-stream-key-2"},
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "30"
    assert second_response.json() == {"detail": "Rate limit exceeded."}
    assert service_state.events.count(("claim_chat_turn",)) == 1


@pytest.mark.asyncio
async def test_security_headers_cover_workspace_static_and_api(
    client: httpx.AsyncClient,
) -> None:
    expected_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=(), microphone=(self), geolocation=()",
    }

    responses = [
        await client.get("/workspace"),
        await client.get("/static/agent-col/app.mjs"),
        await client.get("/api/auth/config"),
    ]

    for response in responses:
        assert response.status_code == 200
        for header, expected_value in expected_headers.items():
            assert response.headers[header] == expected_value
        content_security_policy = response.headers[
            "content-security-policy"
        ]
        assert "script-src 'self' https://accounts.google.com/gsi/client" in (
            content_security_policy
        )
        assert "frame-src https://accounts.google.com/gsi/" in (
            content_security_policy
        )
        assert "connect-src 'self'" in content_security_policy
        assert "media-src 'self' blob:" in content_security_policy
        assert "object-src 'none'" in content_security_policy


@pytest.mark.asyncio
async def test_auth_session_requires_bearer_in_google_mode(
    client: httpx.AsyncClient,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Authorization bearer token is required."
    }


@pytest.mark.asyncio
async def test_auth_config_exposes_only_public_google_settings(
    client: httpx.AsyncClient,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "auth_contract_version": "1.0",
        "auth_mode": "google_oidc",
        "google_client_id": "client-123",
        "google_signin_required": True,
        "local_development": False,
    }


@pytest.mark.asyncio
async def test_auth_session_returns_google_principal(
    client: httpx.AsyncClient,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {
            "sub": "109876543210",
            "email": "user@example.com",
            "name": "WiFi Knight",
        },
    )

    response = await client.get(
        "/api/auth/session",
        headers={"Authorization": "Bearer token-abc"},
    )
    public_user_id = public_user_locator("109876543210")

    assert response.status_code == 200
    assert response.json() == {
        "auth_contract_version": "1.0",
        "auth_mode": "google_oidc",
        "authenticated": True,
        "local_development": False,
        "user_id": public_user_id,
        "workspace_project_id": (
            google_subject_to_workspace_project_id("109876543210")
        ),
        "email": "user@example.com",
        "display_name": "WiFi Knight",
    }


@pytest.mark.asyncio
async def test_google_mode_rejects_project_artifact_mismatch_before_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.get(
        "/api/projects/agent-col/blueprints",
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated user does not own this request."
    }
    assert service_state.artifact_service.list_calls == []


@pytest.mark.asyncio
async def test_workspace_list_returns_owned_containers(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id="agent-col",
                display_name="Agent Col",
                is_default=True,
            )
        ]
    )

    response = await client.get(
        "/api/users/wifiknight/workspaces",
        params={"limit": 10},
    )

    assert response.status_code == 200
    assert response.json() == (
        service_state.database.workspace_list_result.model_dump(mode="json")
    )
    assert service_state.database.workspace_list_calls == [
        ("wifiknight", "agent-col", "Agent Col", 10)
    ]


@pytest.mark.asyncio
async def test_google_workspace_create_uses_subject_owned_workspace_prefix(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    default_workspace_id = google_subject_to_workspace_project_id(
        subject
    )
    workspace_id = f"{default_workspace_id}--study-plans"
    service_state.database.workspace_create_result = WorkspaceSummary(
        workspace_id=workspace_id,
        display_name="Study Plans",
        is_default=False,
    )
    public_user_id = public_user_locator(subject)

    response = await client.post(
        f"/api/users/{public_user_id}/workspaces",
        json={"display_name": "Study Plans"},
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "workspace_contract_version": "1.0",
        "workspace": (
            service_state.database.workspace_create_result.model_dump(
                mode="json"
            )
        ),
    }
    assert service_state.database.workspace_create_calls == [
        (
            "google--109876543210",
            workspace_id,
            WorkspaceCreateRequest(display_name="Study Plans"),
        )
    ]


@pytest.mark.asyncio
async def test_google_mode_rejects_raw_internal_user_locator(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    response = await client.get(
        "/api/users/google--109876543210/workspaces",
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated user does not own this request."
    }
    assert service_state.database.workspace_list_calls == []


@pytest.mark.asyncio
async def test_workspace_delete_returns_no_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.delete(
        "/api/users/wifiknight/workspaces/project--abc--study-plans"
    )

    assert response.status_code == 204
    assert response.content == b""
    assert service_state.database.workspace_delete_calls == [
        ("wifiknight", "project--abc--study-plans", "agent-col", "Agent Col")
    ]


@pytest.mark.asyncio
async def test_google_workspace_delete_uses_effective_owner_and_default(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    public_user_id = public_user_locator(subject)
    default_workspace_id = google_subject_to_workspace_project_id(subject)

    response = await client.delete(
        f"/api/users/{public_user_id}/workspaces/{default_workspace_id}",
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 204
    assert service_state.database.workspace_delete_calls == [
        (
            "google--109876543210",
            default_workspace_id,
            default_workspace_id,
            "Private Google workspace",
        )
    ]


@pytest.mark.asyncio
async def test_workspace_delete_rejects_last_workspace(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.workspace_error = WorkspaceDeletionConflictError(
        "Cannot delete the last workspace."
    )

    response = await client.delete(
        "/api/users/wifiknight/workspaces/agent-col"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "At least one workspace must remain."
    }


@pytest.mark.asyncio
async def test_workspace_delete_missing_workspace_returns_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.workspace_error = WorkspaceNotFoundError(
        "Workspace is unavailable."
    )

    response = await client.delete(
        "/api/users/wifiknight/workspaces/project--missing"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace was not found."}


@pytest.mark.asyncio
async def test_collaborative_note_list_uses_effective_user_and_workspace(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/users/user-1/projects/project-1/notes",
        params={"limit": 10},
    )

    assert response.status_code == 200
    assert response.json() == CollaborativeNoteListResponse(
        notes=service_state.collaborative_note_service.list_result.notes,
        next_note_id=None,
    ).model_dump(mode="json")
    assert service_state.collaborative_note_service.list_calls == [
        ListCollaborativeNotesCommand(
            user_id="user-1",
            workspace_id="project-1",
            status_filter="active",
            limit=10,
            cursor=None,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_detail_returns_note_and_lifecycle_events(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/users/user-1/projects/project-1/notes/note-1",
        params={"limit": 10},
    )

    assert response.status_code == 200
    assert response.json() == CollaborativeNoteDetailResponse(
        note=service_state.collaborative_note_service.detail_result.note,
        events=service_state.collaborative_note_service.detail_result.events,
    ).model_dump(mode="json")
    assert service_state.collaborative_note_service.detail_calls == [
        GetCollaborativeNoteCommand(
            user_id="user-1",
            workspace_id="project-1",
            note_id="note-1",
            limit=10,
        )
    ]


@pytest.mark.asyncio
async def test_google_collaborative_note_responses_hide_internal_owner(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    internal_user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id=project_id,
                display_name="Private Google workspace",
                is_default=True,
            )
        ]
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    note = CollaborativeNote.model_validate(
        {
            **collaborative_note_payload(),
            "owner_user_id": internal_user_id,
            "workspace_id": project_id,
        }
    )
    event = CollaborativeNoteEvent.model_validate(
        {
            **collaborative_note_event_payload(),
            "owner_user_id": internal_user_id,
            "workspace_id": project_id,
        }
    )
    service_state.collaborative_note_service.detail_result = (
        CollaborativeNoteDetailResult(note=note, events=[event])
    )

    response = await client.get(
        f"/api/users/{public_user_id}/projects/{project_id}/notes/note-1",
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["note"]["owner_user_id"] == public_user_id
    assert payload["events"][0]["owner_user_id"] == public_user_id
    assert internal_user_id not in str(payload)
    assert service_state.collaborative_note_service.detail_calls == [
        GetCollaborativeNoteCommand(
            user_id=internal_user_id,
            workspace_id=project_id,
            note_id="note-1",
            limit=20,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_correction_requires_idempotency_key(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/note-1/corrections",
        json={
            "expected_revision": 1,
            "note_kind": "constraint",
            "title": "API version",
            "body": "Use API version 3.",
            "source_session_id": "session-2",
            "source_message_ids": ["user-message-2"],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Idempotency-Key header is required."
    }


@pytest.mark.asyncio
async def test_collaborative_note_correction_returns_pending_proposal(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/note-1/corrections",
        headers={"Idempotency-Key": "idem-note-correction-1"},
        json={
            "expected_revision": 1,
            "note_kind": "constraint",
            "title": "API version",
            "body": "Use API version 3.",
            "source_session_id": "session-2",
            "source_message_ids": ["user-message-2"],
        },
    )

    assert response.status_code == 200
    assert response.json() == CollaborativeNoteProposalResponse(
        proposal=service_state.collaborative_note_service.proposal_result.proposal
    ).model_dump(mode="json")
    assert service_state.collaborative_note_service.correction_calls == [
        CollaborativeNoteCorrectionCommand(
            user_id="user-1",
            workspace_id="project-1",
            note_id="note-1",
            expected_revision=1,
            note_kind="constraint",
            title="API version",
            body="Use API version 3.",
            source_session_id="session-2",
            source_message_ids=("user-message-2",),
            idempotency_key="idem-note-correction-1",
            observed_at=service_state.collaborative_note_service.correction_calls[
                0
            ].observed_at,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_proposal_returns_pending_proposal(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/proposals",
        headers={"Idempotency-Key": "idem-note-proposal-1"},
        json={
            "session_id": "session-1",
            "note_kind": "constraint",
            "title": "API version",
            "body": "Use API version 2.",
        },
    )

    assert response.status_code == 200
    assert response.json() == CollaborativeNoteProposalResponse(
        proposal=service_state.collaborative_note_service.proposal_result.proposal
    ).model_dump(mode="json")
    assert service_state.collaborative_note_service.proposal_calls == [
        CollaborativeNoteProposalCommand(
            user_id="user-1",
            workspace_id="project-1",
            session_id="session-1",
            note_kind="constraint",
            title="API version",
            body="Use API version 2.",
            idempotency_key="idem-note-proposal-1",
            observed_at=service_state.collaborative_note_service.proposal_calls[
                0
            ].observed_at,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_proposal_rejects_invalid_policy_kind(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/proposals",
        headers={"Idempotency-Key": "idem-note-proposal-1"},
        json={
            "session_id": "session-1",
            "note_kind": "preference",
            "title": "API version",
            "body": "Use API version 2.",
        },
    )

    assert response.status_code == 422
    assert service_state.collaborative_note_service.proposal_calls == []


@pytest.mark.asyncio
async def test_collaborative_note_proposal_rejects_prohibited_policy_text(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/proposals",
        headers={"Idempotency-Key": "idem-note-proposal-1"},
        json={
            "session_id": "session-1",
            "note_kind": "constraint",
            "title": "API version",
            "body": "note everything",
        },
    )

    assert response.status_code == 422
    assert service_state.collaborative_note_service.proposal_calls == []


@pytest.mark.asyncio
async def test_collaborative_note_archive_returns_revisioned_note_and_event(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/note-1/archive",
        json={"expected_revision": 1},
    )

    assert response.status_code == 200
    assert response.json() == CollaborativeNoteLifecycleResponse(
        note=service_state.collaborative_note_service.lifecycle_result.note,
        event=service_state.collaborative_note_service.lifecycle_result.event,
    ).model_dump(mode="json")
    assert service_state.collaborative_note_service.archive_calls == [
        CollaborativeNoteLifecycleCommand(
            user_id="user-1",
            workspace_id="project-1",
            note_id="note-1",
            expected_revision=1,
            observed_at=service_state.collaborative_note_service.archive_calls[
                0
            ].observed_at,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_restore_routes_revisioned_command(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/note-1/restore",
        json={"expected_revision": 1},
    )

    assert response.status_code == 200
    assert service_state.collaborative_note_service.restore_calls == [
        CollaborativeNoteLifecycleCommand(
            user_id="user-1",
            workspace_id="project-1",
            note_id="note-1",
            expected_revision=1,
            observed_at=service_state.collaborative_note_service.restore_calls[
                0
            ].observed_at,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_delete_returns_no_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.request(
        "DELETE",
        "/api/users/user-1/projects/project-1/notes/note-1",
        json={"expected_revision": 1},
    )

    assert response.status_code == 204
    assert response.text == ""
    assert service_state.collaborative_note_service.delete_calls == [
        CollaborativeNoteLifecycleCommand(
            user_id="user-1",
            workspace_id="project-1",
            note_id="note-1",
            expected_revision=1,
            observed_at=service_state.collaborative_note_service.delete_calls[
                0
            ].observed_at,
        )
    ]


@pytest.mark.asyncio
async def test_collaborative_note_missing_maps_to_unavailable_response(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.collaborative_note_service.error = MemoryProposalNotFoundError(
        "private note missing detail"
    )

    response = await client.get(
        "/api/users/user-1/projects/project-1/notes/note-1",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Collaborative note was not found."}
    assert "private note missing detail" not in response.text


@pytest.mark.asyncio
async def test_collaborative_note_conflict_maps_to_safe_response(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.collaborative_note_service.error = MemoryProposalConflictError(
        "private stale revision detail"
    )

    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/note-1/archive",
        json={"expected_revision": 1},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Collaborative note state conflicts with this request."
    }
    assert "private stale revision detail" not in response.text


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
async def test_list_chat_sessions_returns_project_user_sessions(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    internal_user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.database.chat_session_list_result = ChatSessionListResponse(
        sessions=[
            ChatSessionSummary(
                session_id="session-1",
                project_id=project_id,
                user_id=internal_user_id,
                updated_at=MEMORY_NOW,
                last_message_preview="Earlier planning question",
                last_message_role="user",
            )
        ]
    )

    response = await client.get(
        f"/api/users/{public_user_id}/projects/{project_id}/chat-sessions",
        headers={"Authorization": "Bearer token-abc"},
        params={"limit": 10},
    )

    assert response.status_code == 200
    assert response.json()["sessions"][0]["user_id"] == public_user_id
    assert internal_user_id not in str(response.json())
    assert service_state.database.chat_session_list_calls == [
        (internal_user_id, project_id, 10)
    ]


@pytest.mark.asyncio
async def test_get_chat_session_detail_returns_chronological_messages(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    internal_user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.database.chat_session_detail_result = (
        ChatSessionDetailResponse(
            session_id="session-1",
            project_id=project_id,
            user_id=internal_user_id,
            messages=[
                ChatMessageRecord(
                    message_id="message-1",
                    role="user",
                    text="hello",
                    timestamp=MEMORY_NOW,
                ),
                ChatMessageRecord(
                    message_id="message-2",
                    role="model",
                    text="hi",
                    timestamp=MEMORY_NOW,
                ),
            ],
            active_memory_clarification=(
                make_memory_clarification_receipt()
            ),
        )
    )

    response = await client.get(
        (
            f"/api/users/{public_user_id}/projects/{project_id}"
            "/chat-sessions/session-1"
        ),
        headers={"Authorization": "Bearer token-abc"},
        params={"limit": 50},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == public_user_id
    assert internal_user_id not in str(response.json())
    assert len(service_state.database.chat_session_detail_calls) == 1
    detail_call = service_state.database.chat_session_detail_calls[0]
    assert detail_call[:4] == (
        internal_user_id,
        project_id,
        "session-1",
        50,
    )
    assert detail_call[4].tzinfo is not None


@pytest.mark.asyncio
async def test_chat_session_routes_validate_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/users/user-1/projects/project-1/chat-sessions",
        params={"limit": 101},
    )

    assert response.status_code == 422
    assert service_state.database.chat_session_list_calls == []


@pytest.mark.asyncio
async def test_agent_job_list_returns_public_owned_projection(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.jobs = [
        make_agent_job(
            status="running",
            lease_owner="worker-private",
            lease_expires_at=MEMORY_NOW + timedelta(minutes=5),
            result_refs={"artifact_id": "artifact-1"},
        )
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs",
        params={"session_id": "session-1", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_job_contract_version"] == "1.0"
    assert payload["jobs"][0]["job_number"] == "001"
    assert payload["jobs"][0]["action_kind"] == "create_artifact"
    assert payload["jobs"][0]["status"] == "running"
    assert payload["jobs"][0]["display_label"] == "Create deployment artifact"
    assert payload["jobs"][0]["agent_label"] == "Artifact Builder"
    forbidden_keys = {
        "job_id",
        "session_id",
        "source_turn_id",
        "source_message_id",
        "workspace_id",
        "result_refs",
        "retry_of_job_id",
    }
    assert forbidden_keys.isdisjoint(payload["jobs"][0])
    assert "worker-private" not in str(payload)
    assert "private-idempotency-key" not in str(payload)
    assert "artifact-1" not in str(payload)
    assert service_state.agent_job_repository.list_calls == [
        {
            "user_id": "user-1",
            "workspace_id": "project-1",
            "project_id": "project-1",
            "session_id": "session-1",
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
async def test_agent_job_stream_emits_public_snapshot(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.jobs = [
        make_agent_job(
            status="running",
            lease_owner="worker-private",
            lease_expires_at=MEMORY_NOW + timedelta(minutes=5),
            result_refs={"artifact_id": "artifact-1"},
        )
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/stream",
        params={"session_id": "session-1", "limit": 50},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in response.text
    assert '"agent_job_contract_version":"1.0"' in response.text
    assert '"status":"running"' in response.text
    assert '"job_number":"001"' in response.text
    assert "agent-job-1" not in response.text
    assert "session-1" not in response.text
    assert "turn-1" not in response.text
    assert "artifact-1" not in response.text
    assert "worker-private" not in response.text
    assert "private-idempotency-key" not in response.text


@pytest.mark.asyncio
async def test_agent_job_stream_rechecks_until_job_reaches_terminal_state(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.job_batches = [
        [make_agent_job(status="running")],
        [make_agent_job(status="completed")],
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/stream",
        params={"session_id": "session-1", "limit": 50},
    )

    assert response.status_code == 200
    assert response.text.count("event: snapshot") >= 2
    assert '"status":"running"' in response.text
    assert '"status":"completed"' in response.text


@pytest.mark.asyncio
async def test_google_agent_job_list_hides_internal_owner(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    internal_user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.agent_job_repository.jobs = [
        make_agent_job(
            user_id=internal_user_id,
            project_id=project_id,
            workspace_id=project_id,
        )
    ]

    response = await client.get(
        f"/api/users/{public_user_id}/projects/{project_id}/agent/jobs",
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"][0]["user_id"] == public_user_id
    assert internal_user_id not in str(payload)
    assert service_state.agent_job_repository.list_calls[0]["user_id"] == (
        internal_user_id
    )


@pytest.mark.asyncio
async def test_agent_job_detail_maps_missing_job_to_sanitized_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.error = AgentJobNotFoundError(
        "private missing marker"
    )

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/missing-job",
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent job was not found."}
    assert "private missing marker" not in response.text


@pytest.mark.asyncio
async def test_agent_job_events_return_only_public_projection(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.events = [
        make_agent_job_event(
            event_id="event-public",
            metadata={"step": "start"},
        ),
        make_agent_job_event(
            event_id="event-private",
            message="Internal prompt prepared.",
            public_visibility=False,
            metadata={},
        ),
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/jobs/agent-job-1/events",
        params={"limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "agent_job_contract_version": "1.0",
        "events": [
            {
                "event_number": "001",
                "event_type": "queued",
                "message": "Queued artifact creation.",
                "created_at": "2026-08-20T23:00:00Z",
                "status": "queued",
                "metadata": {"step": "start"},
            }
        ],
    }
    assert "agent-job-1" not in response.text
    assert "event-public" not in response.text
    assert "event-private" not in response.text
    assert "Internal prompt" not in response.text


@pytest.mark.asyncio
async def test_agent_job_reports_return_public_safe_projection(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.jobs = [
        make_agent_job(job_id="agent-job-1", created_at=MEMORY_NOW),
        make_agent_job(
            job_id="agent-job-2",
            idempotency_key="private-idempotency-key-2",
            created_at=MEMORY_NOW + timedelta(seconds=5),
            updated_at=MEMORY_NOW + timedelta(seconds=5),
        ),
    ]
    service_state.agent_job_repository.reports = [
        make_agent_job_report(
            report_id="agent-job-report-2",
            job_id="agent-job-2",
            title="Memory proposal not created",
            summary="A pending memory proposal already exists for this category.",
            public_resource_label=None,
            status="failed",
            created_at=MEMORY_NOW + timedelta(seconds=20),
        ),
        make_agent_job_report(created_at=MEMORY_NOW + timedelta(seconds=30)),
    ]

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/reports",
        params={"session_id": "session-1", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_job_report_contract_version"] == "1.0"
    assert [report["report_number"] for report in payload["reports"]] == [
        "001",
        "002",
    ]
    assert [report["job_number"] for report in payload["reports"]] == [
        "002",
        "001",
    ]
    assert payload["reports"][1]["summary"] == (
        "A memory proposal was created and is pending your review."
    )
    forbidden_keys = {
        "report_id",
        "job_id",
        "session_id",
        "source_turn_id",
        "source_message_id",
        "workspace_id",
    }
    for report in payload["reports"]:
        assert forbidden_keys.isdisjoint(report)
    assert "agent-job-report" not in str(payload)
    assert "agent-job-" not in str(payload)
    assert "session-1" not in str(payload)


@pytest.mark.asyncio
async def test_agent_job_reports_map_repository_errors_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.agent_job_repository.error = AgentJobRepositoryError(
        "private report marker"
    )

    response = await client.get(
        "/api/users/user-1/projects/project-1/agent/reports",
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Agent job storage operation failed."}
    assert "private report marker" not in response.text


@pytest.mark.asyncio
async def test_agent_job_cancel_returns_cancelled_job_projection(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/agent/jobs/agent-job-1/cancel",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "cancelled"
    assert payload["job"]["job_number"] == "001"
    forbidden_keys = {
        "job_id",
        "session_id",
        "source_turn_id",
        "source_message_id",
        "retry_of_job_id",
    }
    assert forbidden_keys.isdisjoint(payload["job"])
    assert service_state.agent_job_repository.cancel_calls[0]["user_id"] == (
        "user-1"
    )
    assert service_state.agent_job_repository.cancel_calls[0][
        "observed_at"
    ].tzinfo is not None


@pytest.mark.asyncio
async def test_agent_job_retry_requires_idempotency_key(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/agent/jobs/agent-job-1/retry",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Idempotency-Key header is required."
    }
    assert service_state.agent_job_repository.retry_calls == []


@pytest.mark.asyncio
async def test_agent_job_retry_uses_deterministic_retry_job_id(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/projects/project-1/agent/jobs/agent-job-1/retry",
        headers={"Idempotency-Key": "retry-idempotency-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["job_number"] == "001"
    assert "retry_of_job_id" not in payload["job"]
    assert "agent-job-1" not in response.text
    retry_call = service_state.agent_job_repository.retry_calls[0]
    assert retry_call["source_job_id"] == "agent-job-1"
    assert retry_call["idempotency_key"] == "retry-idempotency-key"
    assert retry_call["retry_job_id"].startswith("agent-job-retry-")
    assert "retry-idempotency-key" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            AgentJobConflictError("private conflict marker"),
            409,
            "Agent job request conflicts with existing state.",
        ),
        (
            AgentJobStateError("private state marker"),
            409,
            "Agent job is not in a valid state for this action.",
        ),
        (
            AgentJobRepositoryError("private storage marker"),
            500,
            "Agent job storage operation failed.",
        ),
    ),
)
async def test_agent_job_routes_map_repository_errors_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service_state.agent_job_repository.error = error

    response = await client.post(
        "/api/users/user-1/projects/project-1/agent/jobs/agent-job-1/cancel",
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "private" not in response.text


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
async def test_approve_memory_proposal_uses_memory_api_without_chat_turn(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/users/user-1/memory/proposals/"
        "response_length--proposal-1/approve"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == {
        "action_name": "approve_memory_signal",
        "status": "completed",
    }
    assert body["profile"]["memory_revision"] == 2
    signal = body["profile"]["active_preferences"]["response_length"]
    assert signal == {
        "signal_id": "response_length--proposal-1",
        "category": "response_length",
        "value": "concise",
        "policy_version": "1.0",
        "source_event_id": "response_length--proposal-1--approved",
        "approved_at": "2026-08-20T23:00:00Z",
    }
    assert service_state.memory_service.decision_calls == [
        MemoryDecisionCommand(
            user_id="user-1",
            proposal_id="response_length--proposal-1",
            decision="approve",
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
        )
    ]
    assert service_state.events == [("memory_decision",)]
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_reject_memory_proposal_uses_memory_api_without_chat_turn(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.memory_service.decision_result = (
        TrustedMemoryMutationResult(
            action=AgentActionReceipt(
                action_name="reject_memory_signal",
                status="completed",
            ),
            profile=CollaborationProfile(memory_revision=2),
        )
    )

    response = await client.post(
        "/api/users/user-1/memory/proposals/"
        "response_length--proposal-1/reject"
    )

    assert response.status_code == 200
    assert response.json()["action"] == {
        "action_name": "reject_memory_signal",
        "status": "completed",
    }
    assert service_state.memory_service.decision_calls == [
        MemoryDecisionCommand(
            user_id="user-1",
            proposal_id="response_length--proposal-1",
            decision="reject",
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
        )
    ]
    assert service_state.events == [("memory_decision",)]
    assert service_state.turn_service.calls == []


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
async def test_lifespan_configures_agent_col_logging(
    monkeypatch: pytest.MonkeyPatch,
    service_state: ServiceState,
) -> None:
    calls = 0

    def configure_logging() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(main, "configure_agent_col_logging", configure_logging)

    async with main.lifespan(main.app):
        assert calls == 1


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
async def test_lifespan_injects_memory_and_notes_into_responder_app(
    service_state: ServiceState,
) -> None:
    async with main.lifespan(main.app):
        assert service_state.responder_memory_services == [
            service_state.memory_service
        ]
        assert service_state.responder_note_services == [
            service_state.collaborative_note_service
        ]
        assert service_state.responder_agent_job_repositories == [
            service_state.agent_job_repository
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
        assert len(service_state.artifact_executor_dependencies) == 1
        artifact_executor_dependencies = (
            service_state.artifact_executor_dependencies[0]
        )
        assert artifact_executor_dependencies[:-1] == (
            service_state.synthesis_service,
            service_state.database,
            service_state.artifact_service,
            main.generate_generic_artifact,
            service_state.generic_artifact_service,
            service_state.genai_client,
            service_state.agent_job_repository,
        )
        assert callable(artifact_executor_dependencies[-1])
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
        assert (
            main.app.state.generic_artifact_service
            is service_state.generic_artifact_service
        )
        assert isinstance(
            main.app.state.generic_artifact_creation_service,
            GenericArtifactCreationService,
        )
        assert (
            main.app.state.generic_artifact_generator
            is generate_generic_artifact
        )


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
async def test_list_generic_artifacts_returns_bounded_public_metadata(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/artifacts",
        params={"limit": 10, "before": "artifact-cursor"},
    )

    assert response.status_code == 200
    assert response.json() == (
        service_state.generic_artifact_service.list_result.model_dump(
            mode="json"
        )
    )
    assert service_state.generic_artifact_service.list_calls == [
        ListGenericArtifactsCommand(
            project_id="project-1",
            limit=10,
            before="artifact-cursor",
        )
    ]


@pytest.mark.asyncio
async def test_list_generic_artifacts_can_request_archived_metadata(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/artifacts",
        params={"limit": 10, "lifecycle_status": "archived"},
    )

    assert response.status_code == 200
    assert service_state.generic_artifact_service.list_calls == [
        ListGenericArtifactsCommand(
            project_id="project-1",
            limit=10,
            lifecycle_status="archived",
        )
    ]


@pytest.mark.asyncio
async def test_get_generic_artifact_returns_canonical_detail(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/artifacts/artifact-1"
    )

    assert response.status_code == 200
    assert response.json() == (
        service_state.generic_artifact_service.detail_result.model_dump(
            mode="json"
        )
    )
    assert service_state.generic_artifact_service.detail_calls == [
        GetGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact-1",
        )
    ]


@pytest.mark.asyncio
async def test_archive_generic_artifact_marks_artifact_archived(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/projects/project-1/artifacts/artifact-1/archive"
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["lifecycle_status"] == "archived"
    assert response.json() == (
        SingleFileArtifactLifecycleResponse(
            metadata=(
                service_state.generic_artifact_service
                .detail_result.metadata.model_copy(
                    update={"lifecycle_status": "archived"}
                )
            )
        ).model_dump(mode="json")
    )
    assert service_state.generic_artifact_service.archive_calls == [
        ArchiveGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact-1",
        )
    ]


@pytest.mark.asyncio
async def test_restore_generic_artifact_marks_artifact_active(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/projects/project-1/artifacts/artifact-1/restore"
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["lifecycle_status"] == "active"
    assert service_state.generic_artifact_service.restore_calls == [
        RestoreGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact-1",
        )
    ]


@pytest.mark.asyncio
async def test_delete_generic_artifact_marks_artifact_deleted(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.delete(
        "/api/projects/project-1/artifacts/artifact-1"
    )

    assert response.status_code == 204
    assert service_state.generic_artifact_service.delete_calls == [
        DeleteGenericArtifactCommand(
            project_id="project-1",
            artifact_id="artifact-1",
        )
    ]


@pytest.mark.asyncio
async def test_update_generic_artifact_metadata_returns_updated_metadata(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.patch(
        "/api/projects/project-1/artifacts/artifact-1/metadata",
        json={
            "display_label": "Renamed Password Generator",
            "filename": "renamed_password_generator.py",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["reference"]["display_label"] == (
        "Renamed Password Generator"
    )
    assert body["metadata"]["filename"] == "renamed_password_generator.py"
    assert service_state.generic_artifact_service.update_metadata_calls == [
        UpdateGenericArtifactMetadataCommand(
            project_id="project-1",
            artifact_id="artifact-1",
            display_label="Renamed Password Generator",
            filename="renamed_password_generator.py",
        )
    ]


@pytest.mark.asyncio
async def test_update_generic_artifact_metadata_rejects_empty_payload(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.patch(
        "/api/projects/project-1/artifacts/artifact-1/metadata",
        json={},
    )

    assert response.status_code == 422
    assert service_state.generic_artifact_service.update_metadata_calls == []


@pytest.mark.asyncio
async def test_create_generic_artifact_version_returns_new_artifact(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/projects/project-1/artifacts/artifact-1/versions",
        json={
            "session_id": "session-2",
            "user_id": "user-1",
            "content": "print('updated')\n",
            "filename": "updated_generator.py",
            "display_label": "Updated Generator",
            "summary": "Updated password generator.",
            "originating_turn_id": "turn-2",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reference"]["artifact_id"] == "artifact-version-1"
    assert body["reference"]["display_label"] == "Updated Generator"
    assert body["artifact"]["filename"] == "updated_generator.py"
    assert body["artifact"]["content"] == "print('updated')\n"
    assert service_state.generic_artifact_service.create_version_calls == [
        CreateGenericArtifactVersionCommand(
            project_id="project-1",
            artifact_id="artifact-1",
            session_id="session-2",
            user_id="user-1",
            content="print('updated')\n",
            filename="updated_generator.py",
            display_label="Updated Generator",
            summary="Updated password generator.",
            originating_turn_id="turn-2",
        )
    ]


@pytest.mark.asyncio
async def test_create_generic_artifact_version_rejects_empty_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/projects/project-1/artifacts/artifact-1/versions",
        json={
            "session_id": "session-2",
            "user_id": "user-1",
            "content": "",
        },
    )

    assert response.status_code == 422
    assert service_state.generic_artifact_service.create_version_calls == []


@pytest.mark.asyncio
async def test_create_generic_artifact_generates_persists_and_returns_reference(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    generated_artifact = SingleFileArtifact(
        artifact_family="code",
        format="python",
        filename="password_generator.py",
        content="print('generated')\n",
        summary="Generated password script.",
    )
    reference = ArtifactReference(
        artifact_type="single_file_artifact",
        project_id="project-1",
        artifact_id="artifact-generated",
        schema_version="1.0",
        display_label="Password Generator",
    )
    generator = FakeGenericArtifactGenerator(result=generated_artifact)
    creator = FakeGenericArtifactCreationService(
        result=GenericArtifactCreationResult(
            reference=reference,
            artifact=generated_artifact,
        )
    )
    main.app.state.generic_artifact_generator = generator
    main.app.state.generic_artifact_creation_service = creator

    response = await client.post(
        "/api/projects/project-1/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "artifact_family": "code",
            "format": "python",
            "filename": "password_generator.py",
            "source_text": (
                "Create a Python password generator using secrets."
            ),
            "display_label": "Password Generator",
            "context_messages": ["Use a command-line script."],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "artifact_contract_version": "1.0",
        "reference": reference.model_dump(mode="json"),
        "artifact": generated_artifact.model_dump(mode="json"),
    }
    assert generator.calls == [
        (
            service_state.genai_client,
            GenericArtifactGenerationRequest(
                artifact_family="code",
                artifact_format="python",
                filename="password_generator.py",
                source_text=(
                    "Create a Python password generator using secrets."
                ),
                context_messages=("Use a command-line script.",),
            ),
        )
    ]
    assert creator.calls == [
        GenericArtifactCreationCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            artifact=generated_artifact.model_dump(mode="json"),
            display_label="Password Generator",
            originating_turn_id=None,
        )
    ]


@pytest.mark.asyncio
async def test_create_generic_artifact_rejects_family_format_mismatch(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    generator = FakeGenericArtifactGenerator(
        result=service_state.generic_artifact_service.detail_result.artifact
    )
    creator = FakeGenericArtifactCreationService(
        result=GenericArtifactCreationResult(
            reference=(
                service_state.generic_artifact_service.detail_result.metadata
                .reference
            ),
            artifact=(
                service_state.generic_artifact_service.detail_result.artifact
            ),
        )
    )
    main.app.state.generic_artifact_generator = generator
    main.app.state.generic_artifact_creation_service = creator

    response = await client.post(
        "/api/projects/project-1/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "artifact_family": "code",
            "format": "markdown",
            "filename": "notes.md",
            "source_text": "Create markdown notes.",
        },
    )

    assert response.status_code == 422
    assert generator.calls == []
    assert creator.calls == []


@pytest.mark.asyncio
async def test_create_generic_artifact_rejects_unbounded_context_messages(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    generator = FakeGenericArtifactGenerator(
        result=service_state.generic_artifact_service.detail_result.artifact
    )
    main.app.state.generic_artifact_generator = generator

    response = await client.post(
        "/api/projects/project-1/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "artifact_family": "code",
            "format": "python",
            "filename": "script.py",
            "source_text": "Create a script.",
            "context_messages": [f"context {index}" for index in range(11)],
        },
    )

    assert response.status_code == 422
    assert generator.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            GenericArtifactGenerationTimeoutError("private timeout"),
            504,
            "Artifact generation timed out.",
        ),
        (
            GenericArtifactGenerationError("private provider failure"),
            502,
            "Artifact generation failed.",
        ),
    ),
)
async def test_create_generic_artifact_translates_generation_failures(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    generator = FakeGenericArtifactGenerator(
        result=service_state.generic_artifact_service.detail_result.artifact,
        error=error,
    )
    main.app.state.generic_artifact_generator = generator

    response = await client.post(
        "/api/projects/project-1/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "artifact_family": "code",
            "format": "python",
            "filename": "script.py",
            "source_text": "Create a script.",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert generator.calls == [
        (
            service_state.genai_client,
            GenericArtifactGenerationRequest(
                artifact_family="code",
                artifact_format="python",
                filename="script.py",
                source_text="Create a script.",
                context_messages=(),
            ),
        )
    ]


@pytest.mark.asyncio
async def test_create_generic_artifact_translates_database_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    generated_artifact = SingleFileArtifact(
        artifact_family="document",
        format="markdown",
        filename="notes.md",
        content="# Notes\n",
        summary="Notes",
    )
    generator = FakeGenericArtifactGenerator(result=generated_artifact)
    creator = FakeGenericArtifactCreationService(
        result=GenericArtifactCreationResult(
            reference=(
                service_state.generic_artifact_service.detail_result.metadata
                .reference
            ),
            artifact=generated_artifact,
        ),
        error=main.MemoryEngineError("private database failure"),
    )
    main.app.state.generic_artifact_generator = generator
    main.app.state.generic_artifact_creation_service = creator

    response = await client.post(
        "/api/projects/project-1/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "artifact_family": "document",
            "format": "markdown",
            "filename": "notes.md",
            "source_text": "Create notes.",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert creator.calls == [
        GenericArtifactCreationCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            artifact=generated_artifact.model_dump(mode="json"),
            display_label=None,
            originating_turn_id=None,
        )
    ]


@pytest.mark.asyncio
async def test_google_mode_rejects_generic_artifact_project_mismatch_before_generation(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )
    generator = FakeGenericArtifactGenerator(
        result=service_state.generic_artifact_service.detail_result.artifact
    )
    main.app.state.generic_artifact_generator = generator

    response = await client.post(
        "/api/projects/agent-col/artifacts",
        json={
            "session_id": "session-1",
            "user_id": "google--109876543210",
            "artifact_family": "code",
            "format": "python",
            "filename": "script.py",
            "source_text": "Create a script.",
        },
        headers={"Authorization": "Bearer token-abc"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Authenticated user does not own this request."
    }
    assert generator.calls == []


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
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            ArtifactCursorNotFoundError("missing"),
            404,
            "Artifact cursor was not found.",
        ),
        (
            GenericArtifactReadStateError("invalid"),
            500,
            "Stored artifact is invalid.",
        ),
    ),
)
async def test_list_generic_artifacts_translates_safe_errors(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service_state.generic_artifact_service.list_error = error

    response = await client.get("/api/projects/project-1/artifacts")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    (
        (
            ArtifactNotFoundError("missing"),
            404,
            "Artifact was not found.",
        ),
        (
            GenericArtifactReadStateError("invalid"),
            500,
            "Stored artifact is invalid.",
        ),
    ),
)
async def test_get_generic_artifact_translates_safe_errors(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    service_state.generic_artifact_service.detail_error = error

    response = await client.get("/api/projects/project-1/artifacts/artifact-1")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


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
async def test_list_generic_artifacts_rejects_unbounded_limit(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.get(
        "/api/projects/project-1/artifacts",
        params={"limit": 51},
    )

    assert response.status_code == 422
    assert service_state.generic_artifact_service.list_calls == []


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
            "queued_actions": [],
            "citations": [],
            "memory_proposals": [],
            "memory_clarifications": [],
            "collaborative_note_proposals": [],
            "collaborative_note_events": [],
            "continuity_receipts": [],
            "continuity_choices": [],
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


@pytest.mark.asyncio
async def test_chat_clarification_selection_requires_idempotency_key(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "memory_clarification_selection": {
                "clarification_id": (
                    "memory-clarification--clarification-1"
                ),
                "selected_candidate_index": 0,
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Memory clarification selection requires an idempotency key."
    }
    assert service_state.events == []


@pytest.mark.asyncio
async def test_chat_continuity_selection_requires_idempotency_key(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Use that export note.",
            "continuity_selection": {
                "choice_id": "choice-0",
                "source_kind": "collaborative_note",
                "source_id": "note-export",
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Continuity selection requires an idempotency key."
    }
    assert service_state.events == []


@pytest.mark.asyncio
async def test_chat_resolves_continuity_note_before_turn_service(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    receipt = make_continuity_receipt()
    source_text = ContinuitySourceText(
        source_kind="collaborative_note",
        source_id="note-export",
        title="Export workflow",
        body="Use the CSV export workflow with a preview step.",
        updated_at=MEMORY_NOW,
    )
    service_state.continuity_service.resolution = ContinuityResolution(
        status="resolved",
        receipts=(receipt,),
        source_texts=(source_text,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Use the Export workflow note.",
        },
    )

    assert response.status_code == 200
    assert response.json()["continuity_receipts"] == [
        receipt.model_dump(mode="json")
    ]
    assert response.json()["continuity_choices"] == []
    assert service_state.continuity_service.calls == [
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="project-1",
            session_id="session-1",
            message="Use the Export workflow note.",
            selection=None,
        )
    ]
    turn_command = service_state.turn_service.calls[0]
    continuity_context = "\n".join(
        part.text
        for content in turn_command.model_input_context
        for part in content.parts or ()
        if part.text
    )
    assert "[SERVER_VALIDATED_CONTINUITY_CONTEXT]" in continuity_context
    assert "Export workflow" in continuity_context
    assert "CSV export workflow" in continuity_context

    completed_response = service_state.database.complete_calls
    assert completed_response == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "what was the name of the project we are working on together",
        "what was the name of the project we are working on again",
    ),
)
async def test_chat_stream_injects_real_resolver_note_context_for_natural_project_name_request(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    message: str,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    note = CollaborativeNote.model_validate(
        {
            **collaborative_note_payload(),
            "note_id": "note-netview",
            "owner_user_id": "user-1",
            "workspace_id": "project-1",
            "note_kind": "working_context",
            "title": "Project Name: NetView",
            "body": "The project name is NetView.",
            "status": "active",
            "revision": 1,
        }
    )

    class Store:
        def __init__(self) -> None:
            self.note_calls: list[tuple[str, str, int]] = []
            self.chat_calls: list[tuple[str, str, int]] = []

        async def list_active_collaborative_notes_for_continuity(
            self,
            *,
            user_id: str,
            workspace_id: str,
            limit: int,
        ) -> tuple[CollaborativeNote, ...]:
            self.note_calls.append((user_id, workspace_id, limit))
            return (note,)

        async def list_chat_sessions(
            self,
            *,
            user_id: str,
            project_id: str,
            limit: int,
        ) -> ChatSessionListResponse:
            self.chat_calls.append((user_id, project_id, limit))
            return ChatSessionListResponse(sessions=[])

        async def get_chat_session_detail(
            self,
            *,
            user_id: str,
            project_id: str,
            session_id: str,
            limit: int,
            observed_at: datetime,
        ) -> ChatSessionDetailResponse:
            raise AssertionError("resolved note should not read chat session detail")

    store = Store()
    main.app.state.continuity_service = ContinuityService(store=store)

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": message,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    final = events[-1][1]
    assert final["continuity_receipts"][0]["source_kind"] == "collaborative_note"
    assert final["continuity_receipts"][0]["source_id"] == "note-netview"
    turn_command = service_state.turn_service.calls[0]
    continuity_context = "\n".join(
        part.text
        for content in turn_command.model_input_context
        for part in content.parts or ()
        if part.text
    )
    assert "[SERVER_VALIDATED_CONTINUITY_CONTEXT]" in continuity_context
    assert "Project Name: NetView" in continuity_context
    assert "The project name is NetView." in continuity_context
    assert store.note_calls == [("user-1", "project-1", 50)]
    assert store.chat_calls == []


@pytest.mark.asyncio
async def test_chat_stream_injects_recent_continuity_note_anchor_for_anaphoric_follow_up(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    note = CollaborativeNote.model_validate(
        {
            **collaborative_note_payload(),
            "note_id": "note-netview",
            "owner_user_id": "user-1",
            "workspace_id": "project-1",
            "note_kind": "working_context",
            "title": "Project Name: NetView",
            "body": "NetView is a local network monitor TUI for Bash.",
            "status": "active",
            "revision": 1,
        }
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-netview--rev-1",
        source_kind="collaborative_note",
        source_id="note-netview",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=MEMORY_NOW,
    )

    class Store:
        def __init__(self) -> None:
            self.note_calls: list[tuple[str, str, int]] = []
            self.receipt_calls: list[tuple[str, str, str, int]] = []
            self.chat_calls: list[tuple[str, str, int]] = []

        async def list_recent_session_continuity_receipts(
            self,
            *,
            user_id: str,
            project_id: str,
            session_id: str,
            limit: int,
        ) -> tuple[ContinuitySourceReceipt, ...]:
            self.receipt_calls.append(
                (user_id, project_id, session_id, limit)
            )
            return (receipt,)

        async def list_active_collaborative_notes_for_continuity(
            self,
            *,
            user_id: str,
            workspace_id: str,
            limit: int,
        ) -> tuple[CollaborativeNote, ...]:
            self.note_calls.append((user_id, workspace_id, limit))
            return (note,)

        async def list_chat_sessions(
            self,
            *,
            user_id: str,
            project_id: str,
            limit: int,
        ) -> ChatSessionListResponse:
            self.chat_calls.append((user_id, project_id, limit))
            return ChatSessionListResponse(sessions=[])

        async def get_chat_session_detail(
            self,
            *,
            user_id: str,
            project_id: str,
            session_id: str,
            limit: int,
            observed_at: datetime,
        ) -> ChatSessionDetailResponse:
            raise AssertionError("resolved note should not read chat detail")

    store = Store()
    main.app.state.continuity_service = ContinuityService(store=store)

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "what was it about",
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    final = events[-1][1]
    assert final["continuity_receipts"][0]["source_kind"] == (
        "collaborative_note"
    )
    assert final["continuity_receipts"][0]["source_id"] == "note-netview"
    assert final["continuity_receipts"][0]["match_reason"] == (
        "recent_continuity"
    )
    turn_command = service_state.turn_service.calls[0]
    continuity_context = "\n".join(
        part.text
        for content in turn_command.model_input_context
        for part in content.parts or ()
        if part.text
    )
    assert "[SERVER_VALIDATED_CONTINUITY_CONTEXT]" in continuity_context
    assert (
        "When a source directly answers the current historical or reference "
        "question, answer from that source before asking for clarification."
    ) in continuity_context
    assert "Project Name: NetView" in continuity_context
    assert "local network monitor TUI for Bash" in continuity_context
    assert service_state.database.working_state_calls == [
        ("user-1", "project-1", "session-1")
    ]
    assert store.receipt_calls == [("user-1", "project-1", "session-1", 5)]
    assert store.note_calls == [("user-1", "project-1", 50)]
    assert store.chat_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "uses_recent_anchor"),
    (
        ("what was it going to be written in?", True),
        ("did we pick a language to write it in already?", True),
        ("what language did i want to write it in?", False),
    ),
)
async def test_chat_stream_resolves_related_language_note_and_updates_working_state(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    message: str,
    uses_recent_anchor: bool,
) -> None:
    service_state.database.chat_turn_result = make_chat_turn_claim()
    previous_state = make_working_state_snapshot()
    service_state.database.working_state = previous_state
    name_note = CollaborativeNote.model_validate(
        {
            **collaborative_note_payload(),
            "note_id": "note-netview",
            "owner_user_id": "user-1",
            "workspace_id": "project-1",
            "note_kind": "working_context",
            "title": "Project Name: NetView",
            "body": "The project name is NetView.",
            "status": "active",
            "revision": 1,
        }
    )
    language_note = CollaborativeNote.model_validate(
        {
            **collaborative_note_payload(),
            "note_id": "note-language",
            "owner_user_id": "user-1",
            "workspace_id": "project-1",
            "note_kind": "requirement",
            "title": "Project Language: TypeScript",
            "body": "The project will be written in TypeScript.",
            "status": "active",
            "revision": 1,
        }
    )
    receipt = ContinuitySourceReceipt(
        receipt_id="continuity--note-netview--rev-1",
        source_kind="collaborative_note",
        source_id="note-netview",
        display_label="Used note: Project Name: NetView",
        match_reason="bounded_relevance",
        source_updated_at=MEMORY_NOW,
    )

    class Store:
        def __init__(self) -> None:
            self.note_calls: list[tuple[str, str, int]] = []
            self.receipt_calls: list[tuple[str, str, str, int]] = []
            self.chat_calls: list[tuple[str, str, int]] = []

        async def list_recent_session_continuity_receipts(
            self,
            *,
            user_id: str,
            project_id: str,
            session_id: str,
            limit: int,
        ) -> tuple[ContinuitySourceReceipt, ...]:
            self.receipt_calls.append(
                (user_id, project_id, session_id, limit)
            )
            return (receipt,)

        async def list_active_collaborative_notes_for_continuity(
            self,
            *,
            user_id: str,
            workspace_id: str,
            limit: int,
        ) -> tuple[CollaborativeNote, ...]:
            self.note_calls.append((user_id, workspace_id, limit))
            return (name_note, language_note)

        async def list_chat_sessions(
            self,
            *,
            user_id: str,
            project_id: str,
            limit: int,
        ) -> ChatSessionListResponse:
            self.chat_calls.append((user_id, project_id, limit))
            return ChatSessionListResponse(sessions=[])

        async def get_chat_session_detail(
            self,
            *,
            user_id: str,
            project_id: str,
            session_id: str,
            limit: int,
            observed_at: datetime,
        ) -> ChatSessionDetailResponse:
            raise AssertionError("resolved note should not read chat detail")

    store = Store()
    main.app.state.continuity_service = ContinuityService(store=store)

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "owned-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": message,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    final = events[-1][1]
    assert final["continuity_receipts"][0]["source_id"] == "note-language"
    turn_command = service_state.turn_service.calls[0]
    continuity_context = "\n".join(
        part.text
        for content in turn_command.model_input_context
        for part in content.parts or ()
        if part.text
    )
    assert "Project Language: TypeScript" in continuity_context
    assert "The project will be written in TypeScript." in continuity_context
    assert turn_command.working_state_context is not None
    assert len(service_state.working_state_service.calls) == 1
    update_command = service_state.working_state_service.calls[0]
    assert update_command.previous_state == previous_state
    assert update_command.continuity_source_texts[0].source_id == (
        "note-language"
    )
    assert store.receipt_calls == (
        [("user-1", "project-1", "session-1", 5)]
        if uses_recent_anchor
        else []
    )
    assert store.note_calls == [("user-1", "project-1", 50)]
    assert store.chat_calls == []


@pytest.mark.asyncio
async def test_chat_consults_existing_working_state_on_plain_follow_up_without_update(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.working_state = make_working_state_snapshot(
        current_goal="Keep discussing NetView project details.",
        next_step_hypothesis="Use the recent NetView context when the user says it.",
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "thanks",
        },
    )

    assert response.status_code == 200
    assert service_state.database.working_state_calls == [
        ("user-1", "project-1", "session-1")
    ]
    turn_command = service_state.turn_service.calls[0]
    assert turn_command.working_state_context is not None
    assert "Keep discussing NetView project details." in (
        turn_command.working_state_context
    )
    assert service_state.working_state_service.calls == []
    assert service_state.database.working_state_save_calls == []


@pytest.mark.asyncio
async def test_chat_returns_continuity_choices_without_model_context(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = claim
    choice = make_continuity_choice()
    alternate_choice = make_alternate_continuity_choice()
    service_state.continuity_service.resolution = ContinuityResolution(
        status="ambiguous",
        choices=(choice, alternate_choice),
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "continuity-choice-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Use that saved note.",
        },
    )

    assert response.status_code == 200
    assert response.json()["continuity_receipts"] == []
    assert response.json()["continuity_choices"] == [
        choice.model_dump(mode="json"),
        alternate_choice.model_dump(mode="json"),
    ]
    assert service_state.turn_service.calls == []
    assert len(service_state.database.complete_calls) == 1
    stored_response = service_state.database.complete_calls[0][1]
    assert stored_response.continuity_choices == [choice, alternate_choice]
    assert service_state.events[-1] == ("complete_chat_turn",)


@pytest.mark.asyncio
async def test_chat_labels_ambiguous_prior_chat_choices(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = claim
    choice = make_chat_session_continuity_choice()
    alternate_choice = make_alternate_chat_session_continuity_choice()
    service_state.continuity_service.resolution = ContinuityResolution(
        status="ambiguous",
        choices=(choice, alternate_choice),
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "continuity-chat-choice-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "What was that HIDS we talked about recently?",
        },
    )

    assert response.status_code == 200
    assert "prior chat" in response.json()["response"]
    assert "saved workspace note" not in response.json()["response"]
    assert response.json()["continuity_choices"] == [
        choice.model_dump(mode="json"),
        alternate_choice.model_dump(mode="json"),
    ]


@pytest.mark.asyncio
async def test_chat_continuity_selection_is_claimed_and_resolved(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = ContinuitySelectionRequest(
        choice_id="choice-0",
        source_kind="collaborative_note",
        source_id="note-export",
    )
    claim = make_chat_turn_claim(continuity_selection=selection)
    service_state.database.chat_turn_result = claim
    receipt = make_continuity_receipt()
    source_text = ContinuitySourceText(
        source_kind="collaborative_note",
        source_id="note-export",
        title="Export workflow",
        body="Use the CSV export workflow with a preview step.",
        updated_at=MEMORY_NOW,
    )
    service_state.continuity_service.resolution = ContinuityResolution(
        status="resolved",
        receipts=(receipt,),
        source_texts=(source_text,),
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "continuity-selection-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Use that export note.",
            "continuity_selection": selection.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert service_state.database.claim_calls[0][0].continuity_selection == (
        selection
    )
    assert service_state.continuity_service.calls[0].selection == selection
    assert response.json()["continuity_receipts"] == [
        receipt.model_dump(mode="json")
    ]


@pytest.mark.asyncio
async def test_chat_clarification_selection_returns_and_replays_proposal(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=0,
    )
    claim = make_chat_turn_claim(
        memory_clarification_selection=selection
    )
    service_state.database.chat_turn_result = claim
    headers = {"Idempotency-Key": "clarification-selection-key-1"}
    payload = {
        "project_id": "project-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "message": "New question",
        "memory_clarification_selection": selection.model_dump(mode="json"),
    }

    response = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "action_name": "propose_memory_signal",
            "status": "completed",
        }
    ]
    assert response.json()["memory_proposals"] == [
        {
            "proposal_id": "response_length--clarified-proposal-1",
            "category": "response_length",
            "proposed_value": "detailed",
            "policy_version": "2.0",
            "expires_at": "2026-08-21T23:00:00Z",
        }
    ]
    assert service_state.database.claim_calls[0][0] == claim.request
    assert service_state.memory_service.selection_calls == [
        SelectMemoryClarificationCommand(
            user_id="user-1",
            workspace_id="project-1",
            session_id="session-1",
            source_message_id=f"turn--{DEFAULT_TURN_ID}--user",
            clarification_id=(
                "memory-clarification--clarification-1"
            ),
            selected_candidate_index=0,
            turn_lease=ProposalTurnLease(
                turn_id=DEFAULT_TURN_ID,
                owner_token="owner-token-1",
            ),
        )
    ]
    turn_command = service_state.turn_service.calls[0]
    assert turn_command.memory_decision_present is True
    assert turn_command.precompleted_actions == (
        service_state.memory_service.selection_result.action,
    )
    assert turn_command.precompleted_memory_proposals == (
        service_state.memory_service.selection_result.proposal,
    )

    stored_response = service_state.database.complete_calls[0][1]
    service_state.database.chat_turn_result = ChatTurnReplay(
        response=stored_response
    )
    event_count = len(service_state.events)

    replay = await client.post(
        "/api/chat",
        headers=headers,
        json=payload,
    )

    assert replay.status_code == 200
    assert replay.json() == response.json()
    assert service_state.events[event_count:] == [("claim_chat_turn",)]
    assert len(service_state.memory_service.selection_calls) == 1


@pytest.mark.asyncio
async def test_chat_clarification_selection_returns_fallback_when_responder_fails_after_proposal(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=0,
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        memory_clarification_selection=selection
    )
    service_state.turn_service.error = AgentColTurnServiceError(
        "private responder failure"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "clarification-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "memory_clarification_selection": selection.model_dump(
                mode="json"
            ),
        },
    )

    assert response.status_code == 200
    assert "pending memory proposal" in response.json()["response"]
    assert response.json()["actions"] == [
        {
            "action_name": "propose_memory_signal",
            "status": "completed",
        }
    ]
    assert response.json()["memory_proposals"][0]["proposal_id"] == (
        "response_length--clarified-proposal-1"
    )
    assert service_state.database.release_calls == []
    assert len(service_state.database.complete_calls) == 1
    completed_response = service_state.database.complete_calls[0][1]
    assert "pending memory proposal" in completed_response.response
    assert completed_response.memory_proposals == [
        service_state.memory_service.selection_result.proposal
    ]


@pytest.mark.asyncio
async def test_chat_clarification_selection_maps_stale_state_to_conflict(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=0,
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        memory_clarification_selection=selection
    )
    service_state.memory_service.error = MemoryClarificationSelectionError(
        "private stale selection"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "clarification-conflict-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "memory_clarification_selection": selection.model_dump(
                mode="json"
            ),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Memory clarification cannot be selected."
    }
    assert len(service_state.database.release_calls) == 1
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_clarification_selection_maps_corrupt_state_safely(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=0,
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        memory_clarification_selection=selection
    )
    service_state.memory_service.error = ChatTurnStateError(
        "private corrupt turn state"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "clarification-state-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "memory_clarification_selection": selection.model_dump(
                mode="json"
            ),
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Chat turn state is invalid."}
    assert "private corrupt turn state" not in response.text
    assert len(service_state.database.release_calls) == 1
    assert service_state.turn_service.calls == []


@pytest.mark.asyncio
async def test_chat_clarification_selection_hides_ownership_mismatch(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    selection = MemoryClarificationSelectionRequest(
        clarification_id="memory-clarification--clarification-1",
        selected_candidate_index=0,
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        memory_clarification_selection=selection
    )
    service_state.memory_service.error = ChatSessionOwnershipError(
        "private clarification owner"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "clarification-owner-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
            "memory_clarification_selection": selection.model_dump(
                mode="json"
            ),
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat session is unavailable."}
    assert "private clarification owner" not in response.text
    assert len(service_state.database.release_calls) == 1
    assert service_state.turn_service.calls == []


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
            "queued_actions": [],
            "citations": [],
        "memory_proposals": [],
        "memory_clarifications": [],
        "collaborative_note_proposals": [],
        "collaborative_note_events": [],
        "continuity_receipts": [],
        "continuity_choices": [],
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
        ("continuity_service",),
        ("working_state", "session-1"),
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
async def test_chat_uses_hidden_working_state_without_public_response_fields(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.database.history = [
        {"role": "user", "text": f"Earlier question {index}"}
        for index in range(10)
    ]
    previous_state = make_working_state_snapshot()
    updated_state = make_working_state_snapshot(
        request_summary="Artifact creation plan after user correction.",
        current_goal="Create a durable artifact from the current request.",
        next_step_hypothesis="Ask only if artifact format becomes blocking.",
    )
    service_state.database.working_state = previous_state
    service_state.working_state_service.result = WorkingStateUpdateResult(
        update_required=True,
        snapshot=updated_state,
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": (
                "I want a deployment plan, probably Cloud Run, but security "
                "matters more than speed."
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Generated answer"
    assert "working_state" not in body
    assert "model_thoughts" not in body
    await wait_for_working_state_background_tasks()
    assert service_state.database.working_state_calls == [
        ("user-1", "project-1", "session-1")
    ]
    assert len(service_state.turn_service.calls) == 1
    turn_command = service_state.turn_service.calls[0]
    assert turn_command.working_state_context is not None
    assert "[SERVER_VALIDATED_WORKING_STATE]" in (
        turn_command.working_state_context
    )
    assert "non-authoritative" in turn_command.working_state_context
    assert "security matters more than speed" in (
        turn_command.working_state_context
    )

    assert len(service_state.working_state_service.calls) == 1
    update_command = service_state.working_state_service.calls[0]
    assert update_command.user_id == "user-1"
    assert update_command.project_id == "project-1"
    assert update_command.session_id == "session-1"
    assert update_command.source_message_id == "user-message-1"
    assert update_command.current_message.startswith(
        "I want a deployment plan"
    )
    assert update_command.model_response == "Generated answer"
    assert update_command.previous_state == previous_state
    assert update_command.recent_user_messages == tuple(
        f"Earlier question {index}" for index in range(2, 10)
    )
    assert len(service_state.database.working_state_save_calls) == 1
    saved_state, observed_at = service_state.database.working_state_save_calls[0]
    assert saved_state == updated_state
    assert observed_at.tzinfo is not None


@pytest.mark.asyncio
async def test_chat_records_preference_observation_without_active_memory(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    from preference_learning import PreferenceObservation
    from preference_learning_service import PreferenceLearningResult

    service_state.database.chat_turn_result = make_chat_turn_claim()
    observation = PreferenceObservation(
        observation_id=f"pref-obs--{DEFAULT_TURN_ID}",
        user_id="user-1",
        project_id="project-1",
        session_id="session-1",
        source_turn_id=DEFAULT_TURN_ID,
        source_message_id=f"turn--{DEFAULT_TURN_ID}--user",
        category="response_length",
        canonical_value="concise",
        evidence_kind="user_correction",
        evidence_summary="User corrected the response to be shorter.",
        confidence_delta=0.35,
        created_at=MEMORY_NOW,
    )
    service_state.preference_learning_service.result = (
        PreferenceLearningResult(observation=observation)
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "pref-chat-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "That was too long; be shorter here.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["memory_proposals"] == []
    assert body["memory_clarifications"] == []
    assert body["adaptations"] == []
    assert len(service_state.preference_learning_service.calls) == 1
    command = service_state.preference_learning_service.calls[0]
    assert command.user_id == "user-1"
    assert command.project_id == "project-1"
    assert command.session_id == "session-1"
    assert command.turn_id == DEFAULT_TURN_ID
    assert command.source_message_id == f"turn--{DEFAULT_TURN_ID}--user"
    assert command.user_message == "That was too long; be shorter here."
    assert command.model_response == "Generated answer"


@pytest.mark.asyncio
async def test_chat_surfaces_preference_confirmation_without_saving_memory(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    from preference_learning import PreferenceHypothesis
    from preference_learning_service import PreferenceLearningResult

    service_state.database.chat_turn_result = make_chat_turn_claim()
    hypothesis = PreferenceHypothesis(
        hypothesis_id="pref-hyp--user-1--project-1--response_length",
        user_id="user-1",
        project_id="project-1",
        category="response_length",
        canonical_value="concise",
        evidence_count=2,
        contradiction_count=0,
        confidence=0.75,
        source_observation_ids=("pref-obs--turn-1", "pref-obs--turn-2"),
        first_observed_at=MEMORY_NOW,
        last_observed_at=MEMORY_NOW,
    )
    clarification = MemoryClarificationReceipt(
        clarification_id="memory-clarification--pref-hyp-1",
        choices=[
            MemoryClarificationChoice(
                candidate_index=0,
                category_label="Response length",
                value_label="concise",
            ),
            MemoryClarificationChoice(
                candidate_index=1,
                category_label="Do not save",
                value_label="Keep this as feedback only",
            ),
        ],
        expires_at=MEMORY_NOW + timedelta(minutes=15),
    )
    service_state.preference_learning_service.result = (
        PreferenceLearningResult(surfaced_hypothesis=hypothesis)
    )
    service_state.memory_service.preference_confirmation_result = clarification

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "pref-chat-key-2"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Again, concise practical answers please.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["memory_clarifications"] == [
        clarification.model_dump(mode="json")
    ]
    assert body["memory_proposals"] == []
    assert body["adaptations"] == []
    assert len(service_state.memory_service.preference_confirmation_calls) == 1
    confirmation_call = (
        service_state.memory_service.preference_confirmation_calls[0]
    )
    assert confirmation_call["user_id"] == "user-1"
    assert confirmation_call["project_id"] == "project-1"
    assert confirmation_call["session_id"] == "session-1"
    assert confirmation_call["source_message_id"] == (
        f"turn--{DEFAULT_TURN_ID}--user"
    )
    assert confirmation_call["hypothesis"] == hypothesis


@pytest.mark.asyncio
async def test_chat_does_not_capture_preference_on_replay_or_structured_decision(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = MemoryDecisionRequest(
        proposal_id="response_length--proposal-1",
        decision="approve",
    )
    service_state.database.chat_turn_result = make_chat_turn_claim(
        memory_decision=decision,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "pref-chat-key-3"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Approve this memory.",
            "memory_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert service_state.preference_learning_service.calls == []
    completed_response = ChatResponse(
        response="Replay answer",
        memory_clarifications=[],
        memory_proposals=[],
    )
    service_state.database.chat_turn_result = ChatTurnReplay(
        response=completed_response,
    )

    replay = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "pref-chat-key-4"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "That was too long; be shorter here.",
        },
    )

    assert replay.status_code == 200
    assert replay.json()["response"] == "Replay answer"
    assert service_state.preference_learning_service.calls == []


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


@pytest.mark.asyncio
async def test_headerless_chat_returns_collaborative_note_proposal(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    proposal = CollaborativeNoteProposal.model_validate(
        {
            **collaborative_note_proposal_payload(),
            "body": "Use API version 2.",
            "expected_note_id": None,
            "expected_revision": None,
        }
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="I created a pending workspace note for your review.",
        actions=(
            AgentActionReceipt(
                action_name="propose_collaborative_note",
                status="completed",
            ),
        ),
        collaborative_note_proposals=(proposal,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": (
                "Agent Col, note that this workspace must use API version 2."
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "action_name": "propose_collaborative_note",
            "status": "completed",
        }
    ]
    assert response.json()["memory_proposals"] == []
    assert response.json()["collaborative_note_proposals"] == [
        proposal.model_dump(mode="json")
    ]
    context = service_state.turn_service.calls[0]
    assert context.source_message_id == "user-message-1"
    assert context.memory_decision_present is False
    assert context.collaborative_note_decision_present is False


@pytest.mark.asyncio
async def test_chat_returns_authoritative_memory_clarification_receipt(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    clarification = make_memory_clarification_receipt()
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Which preference did you mean?",
        memory_clarifications=(clarification,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Please remember that I prefer detailed guidance.",
        },
    )

    assert response.status_code == 200
    assert response.json()["memory_clarifications"] == [
        clarification.model_dump(mode="json")
    ]


@pytest.mark.asyncio
async def test_chat_preflights_ambiguous_memory_request_into_clarification(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    prompt = (
        "Please remember one of these preferences, but help me choose which "
        "one to save: I prefer practical examples whenever helpful, or I "
        "prefer Agent Col to ask fewer follow-up questions and make "
        "reasonable assumptions."
    )
    clarification = make_memory_clarification_receipt()
    service_state.memory_service.natural_memory_result = (
        NaturalMemoryClarificationResult(
            status="clarification_required",
            clarification=clarification,
        )
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="Please choose one."
    )
    service_state.database.chat_turn_result = make_chat_turn_claim()

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "memory-clarification-preflight-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": prompt,
        },
    )

    assert response.status_code == 200
    assert response.json()["memory_clarifications"] == [
        clarification.model_dump(mode="json")
    ]
    assert len(service_state.memory_service.natural_memory_calls) == 1
    natural_call = service_state.memory_service.natural_memory_calls[0]
    assert natural_call.user_id == "user-1"
    assert natural_call.workspace_id == "project-1"
    assert natural_call.session_id == "session-1"
    assert natural_call.source_message_id == f"turn--{DEFAULT_TURN_ID}--user"
    assert natural_call.source_message_text == prompt
    assert natural_call.memory_decision_present is False
    assert natural_call.turn_lease == ProposalTurnLease(
        turn_id=DEFAULT_TURN_ID,
        owner_token="owner-token-1",
    )
    assert natural_call.decision.kind == "clarify"
    assert [
        (candidate.category, candidate.canonical_value)
        for candidate in natural_call.decision.candidates
    ] == [
        ("example_usage", "when_helpful"),
        ("question_style", "minimal_follow_up"),
    ]
    assert service_state.turn_service.calls[0].precompleted_memory_clarifications == (
        clarification,
    )


@pytest.mark.asyncio
async def test_chat_preflight_clarification_returns_fallback_when_responder_fails(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    prompt = (
        "Please remember one of these preferences, but help me choose which "
        "one to save: I prefer practical examples whenever helpful, or I "
        "prefer Agent Col to ask fewer follow-up questions and make "
        "reasonable assumptions."
    )
    clarification = make_memory_clarification_receipt()
    claim = make_chat_turn_claim()
    service_state.memory_service.natural_memory_result = (
        NaturalMemoryClarificationResult(
            status="clarification_required",
            clarification=clarification,
        )
    )
    service_state.database.chat_turn_result = claim
    service_state.turn_service.error = AgentColTurnResponderError(
        "private provider failure"
    )

    response = await client.post(
        "/api/chat",
        headers={
            "Idempotency-Key": "memory-clarification-preflight-fallback-1"
        },
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": prompt,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": (
            "I found more than one possible memory preference in your "
            "message. Please choose one option below so I can submit the "
            "correct pending memory proposal for your approval."
        ),
        "actions": [],
        "artifacts": [],
        "artifact_feedback": [],
        "queued_actions": [],
        "citations": [],
        "memory_proposals": [],
        "memory_clarifications": [clarification.model_dump(mode="json")],
        "collaborative_note_proposals": [],
        "collaborative_note_events": [],
        "continuity_receipts": [],
        "continuity_choices": [],
        "adaptations": [],
    }
    assert len(service_state.database.complete_calls) == 1
    completed_claim, completed_response, completed_at = (
        service_state.database.complete_calls[0]
    )
    assert completed_claim == claim
    assert completed_response.model_dump(mode="json") == response.json()
    assert completed_at.tzinfo is not None
    assert service_state.database.release_calls == []


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
async def test_google_chat_requires_idempotency_key_before_service_access(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )

    response = await client.post(
        "/api/chat",
        headers={"Authorization": "Bearer token-abc"},
        json={
            "project_id": google_subject_to_workspace_project_id(subject),
            "session_id": "private-google-session",
            "user_id": public_user_locator(subject),
            "message": "private-google-message",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Google-authenticated chat requires an idempotency key."
    }
    assert service_state.events == []
    assert service_state.database.history_calls == []
    assert service_state.database.save_calls == []
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


@pytest.mark.parametrize(
    "failure_operation",
    ("claim", "history", "save_user", "save_model"),
)
@pytest.mark.asyncio
async def test_chat_translates_session_ownership_errors_to_uniform_not_found(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
    failure_operation: str,
) -> None:
    headers: dict[str, str] = {}
    if failure_operation == "claim":
        headers["Idempotency-Key"] = "private-ownership-key"
        service_state.database.chat_turn_error = ChatSessionOwnershipError(
            "private-claim-ownership-marker"
        )
    else:
        service_state.database.session_ownership_error_at = failure_operation

    response = await client.post(
        "/api/chat",
        headers=headers,
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "private-message-marker",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat session is unavailable."}
    if failure_operation in {"claim", "history", "save_user"}:
        assert service_state.turn_service.calls == []
    if failure_operation == "claim":
        assert service_state.database.history_calls == []
        assert service_state.database.save_calls == []
    if failure_operation == "history":
        assert service_state.database.save_calls == []
    if failure_operation == "save_user":
        assert service_state.database.save_calls[-1][1] == "user"
    if failure_operation == "save_model":
        assert [call[1] for call in service_state.database.save_calls] == [
            "user",
            "model",
        ]
    for private_marker in (
        "private-ownership-key",
        "private-project",
        "private-session",
        "private-user",
        "private-message-marker",
        "private-claim-ownership-marker",
        "private-history-ownership-marker",
        "private-user-save-ownership-marker",
        "private-model-save-ownership-marker",
    ):
        assert private_marker not in caplog.text


@pytest.mark.asyncio
async def test_headerless_local_chat_propagates_session_owner_to_all_io(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
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
    assert service_state.database.history_calls == [
        ("session-1", 20, "user-1", "project-1", None)
    ]
    assert service_state.database.save_calls == [
        ("session-1", "user", "New question", "project-1", "user-1"),
        (
            "session-1",
            "model",
            "Generated answer",
            "project-1",
            "user-1",
        ),
    ]


@pytest.mark.asyncio
async def test_google_chat_propagates_verified_owner_to_claim_and_history(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id=project_id,
                display_name="Private Google workspace",
                is_default=True,
            )
        ]
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.database.chat_turn_result = make_chat_turn_claim()

    response = await client.post(
        "/api/chat",
        headers={
            "Authorization": "Bearer token-abc",
            "Idempotency-Key": "google-owned-key-1",
        },
        json={
            "project_id": project_id,
            "session_id": "google-session-1",
            "user_id": public_user_id,
            "message": "New question",
        },
    )

    assert response.status_code == 200
    assert service_state.database.claim_calls[0][0].user_id == user_id
    assert service_state.database.claim_calls[0][0].project_id == project_id
    assert service_state.database.history_calls == [
        (
            "google-session-1",
            20,
            user_id,
            project_id,
            f"turn--{DEFAULT_TURN_ID}--user",
        )
    ]
    assert service_state.database.save_calls == []


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
        ("continuity_service",),
        ("working_state", "session-1"),
        ("renew_chat_turn_lease",),
        ("turn_service",),
        ("preference_learning",),
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
    caplog: pytest.LogCaptureFixture,
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
    caplog.set_level(logging.INFO, logger=main.logger.name)

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "artifact-failure-key-1"},
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "private script request marker",
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
    assert "Agent_Col chat pipeline" in caplog.text
    assert "stage=turn_service_failure" in caplog.text
    assert "route=chat_json" in caplog.text
    assert "error=AgentColTurnResponderError" in caplog.text
    assert "completed_actions=1" in caplog.text
    assert "artifacts=1" in caplog.text
    for private_marker in (
        "private responder failure",
        "private-project",
        "private-session",
        "private-user",
        "private script request marker",
    ):
        assert private_marker not in caplog.text


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
async def test_direct_artifact_feedback_does_not_use_chat_turn(
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
    action = AgentActionReceipt(
        action_name="record_blueprint_feedback",
        status="completed",
    )
    feedback = ArtifactFeedbackReference(
        feedback_id="feedback--artifact-feedback-key-2",
        artifact_id="blueprint-1",
        target_id="target--0123456789abcdef01234567",
        target_kind="whole_blueprint",
        decision="accepted",
        schema_version="2.0",
        created_at=MEMORY_NOW,
    )
    service_state.artifact_feedback_service.record_result = (
        RecordBlueprintFeedbackResult(action=action, feedback=feedback)
    )

    response = await client.post(
        "/api/projects/project-1/blueprints/blueprint-1/feedback",
        headers={"Idempotency-Key": "artifact-feedback-key-2"},
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            **decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == action.model_dump(mode="json")
    assert response.json()["feedback"] == feedback.model_dump(mode="json")
    assert service_state.artifact_feedback_service.record_calls == [
        RecordBlueprintFeedbackCommand(
            project_id="project-1",
            session_id="session-1",
            user_id="user-1",
            source_message_id="artifact-feedback-key-2",
            turn_id="artifact-feedback-key-2",
            feedback=decision,
            observed_at=(
                service_state.artifact_feedback_service.record_calls[0]
                .observed_at
            ),
        )
    ]
    assert service_state.database.claim_calls == []
    assert service_state.turn_service.calls == []
    assert service_state.database.complete_calls == []


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
async def test_chat_requires_idempotency_key_for_collaborative_note_decision(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Approve that note.",
            "collaborative_note_decision": {
                "proposal_id": "note-proposal-1",
                "decision": "approve",
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Collaborative note decision requires an idempotency key."
    }
    assert service_state.events == []


@pytest.mark.asyncio
async def test_direct_collaborative_note_decision_does_not_use_chat_turn(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    action = AgentActionReceipt(
        action_name="approve_collaborative_note",
        status="completed",
    )
    event = CollaborativeNoteEvent.model_validate(
        collaborative_note_event_payload("approved")
    )
    service_state.collaborative_note_service.decision_result = (
        CollaborativeNoteDecisionResult(
            action=action,
            note=CollaborativeNote.model_validate(
                collaborative_note_payload()
            ),
            event=event,
        )
    )

    response = await client.post(
        "/api/users/user-1/projects/project-1/notes/proposals/"
        "note-proposal-1/approve"
    )

    assert response.status_code == 200
    assert response.json()["action"] == action.model_dump(mode="json")
    assert response.json()["event"] == event.model_dump(mode="json")
    assert service_state.collaborative_note_service.decision_calls == [
        CollaborativeNoteDecisionCommand(
            user_id="user-1",
            workspace_id="project-1",
            proposal_id="note-proposal-1",
            decision="approve",
            observed_at=(
                service_state.collaborative_note_service.decision_calls[0]
                .observed_at
            ),
        )
    ]
    assert service_state.database.claim_calls == []
    assert service_state.turn_service.calls == []
    assert service_state.database.complete_calls == []


@pytest.mark.asyncio
async def test_chat_completes_structured_collaborative_note_decision_turn(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = CollaborativeNoteDecisionRequest(
        proposal_id="note-proposal-1",
        decision="approve",
    )
    claim = make_chat_turn_claim(collaborative_note_decision=decision)
    renewed_claim = replace(
        claim,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
    )
    action = AgentActionReceipt(
        action_name="approve_collaborative_note",
        status="completed",
    )
    event = CollaborativeNoteEvent.model_validate(
        collaborative_note_event_payload("approved")
    )
    effect_claim = replace(
        renewed_claim,
        precompleted_actions=(action,),
        precompleted_collaborative_note_events=(event,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.collaborative_note_service.decision_result = (
        CollaborativeNoteDecisionResult(
            action=action,
            note=CollaborativeNote.model_validate(
                collaborative_note_payload()
            ),
            event=event,
        )
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="I recorded that note.",
        actions=(action,),
        collaborative_note_events=(event,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "note-decision-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Approve that note.",
            "collaborative_note_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["actions"] == [action.model_dump(mode="json")]
    assert response.json()["collaborative_note_events"] == [
        event.model_dump(mode="json")
    ]
    assert service_state.collaborative_note_service.decision_calls == [
        CollaborativeNoteDecisionCommand(
            user_id="user-1",
            workspace_id="project-1",
            proposal_id="note-proposal-1",
            decision="approve",
            observed_at=service_state.collaborative_note_service.decision_calls[
                0
            ].observed_at,
        )
    ]
    turn_request = service_state.database.claim_calls[0][0]
    assert turn_request.collaborative_note_decision == decision
    assert service_state.database.note_decision_effect_calls == [
        (
            claim,
            event,
            service_state.database.note_decision_effect_calls[0][2],
        )
    ]
    command = service_state.turn_service.calls[0]
    assert command.collaborative_note_decision_present is True
    assert command.precompleted_collaborative_note_events == (event,)
    assert service_state.database.complete_calls[0][0] is effect_claim
    assert service_state.database.complete_calls[0][1].collaborative_note_events == [
        event
    ]


@pytest.mark.asyncio
async def test_google_chat_note_event_receipts_hide_internal_owner(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    subject = "109876543210"
    internal_user_id = f"google--{subject}"
    public_user_id = public_user_locator(subject)
    project_id = google_subject_to_workspace_project_id(subject)
    service_state.database.workspace_list_result = WorkspaceListResponse(
        workspaces=[
            WorkspaceSummary(
                workspace_id=project_id,
                display_name="Private Google workspace",
                is_default=True,
            )
        ]
    )
    decision = CollaborativeNoteDecisionRequest(
        proposal_id="note-proposal-1",
        decision="approve",
    )
    claim = make_chat_turn_claim(collaborative_note_decision=decision)
    renewed_claim = replace(
        claim,
        lease_expires_at=MEMORY_NOW + timedelta(seconds=240),
    )
    action = AgentActionReceipt(
        action_name="approve_collaborative_note",
        status="completed",
    )
    event = CollaborativeNoteEvent.model_validate(
        {
            **collaborative_note_event_payload("approved"),
            "owner_user_id": internal_user_id,
            "workspace_id": project_id,
        }
    )
    effect_claim = replace(
        renewed_claim,
        precompleted_actions=(action,),
        precompleted_collaborative_note_events=(event,),
    )
    main.app.state.authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": subject},
    )
    service_state.database.chat_turn_result = claim
    service_state.database.renewed_claim = renewed_claim
    service_state.collaborative_note_service.decision_result = (
        CollaborativeNoteDecisionResult(
            action=action,
            note=CollaborativeNote.model_validate(
                {
                    **collaborative_note_payload(),
                    "owner_user_id": internal_user_id,
                    "workspace_id": project_id,
                }
            ),
            event=event,
        )
    )
    service_state.turn_service.turn_result = AgentColTurnResult(
        response="I recorded that note.",
        actions=(action,),
        collaborative_note_events=(event,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={
            "Authorization": "Bearer token-abc",
            "Idempotency-Key": "google-note-decision-key-1",
        },
        json={
            "project_id": project_id,
            "session_id": "session-1",
            "user_id": public_user_id,
            "message": "Approve that note.",
            "collaborative_note_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["collaborative_note_events"][0]["owner_user_id"]
        == public_user_id
    )
    assert internal_user_id not in str(payload)
    assert service_state.collaborative_note_service.decision_calls[0].user_id == (
        internal_user_id
    )
    assert service_state.database.complete_calls[0][1].collaborative_note_events == [
        event
    ]


@pytest.mark.asyncio
async def test_note_decision_responder_failure_returns_completed_receipt(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    decision = CollaborativeNoteDecisionRequest(
        proposal_id="note-proposal-1",
        decision="reject",
    )
    claim = make_chat_turn_claim(collaborative_note_decision=decision)
    action = AgentActionReceipt(
        action_name="reject_collaborative_note",
        status="completed",
    )
    event = CollaborativeNoteEvent.model_validate(
        {
            **collaborative_note_event_payload("rejected"),
            "note_kind": None,
            "title": None,
            "body": None,
            "source_session_id": None,
            "source_message_ids": [],
        }
    )
    effect_claim = replace(
        claim,
        precompleted_actions=(action,),
        precompleted_collaborative_note_events=(event,),
    )
    service_state.database.chat_turn_result = claim
    service_state.database.released_claim = effect_claim
    service_state.collaborative_note_service.decision_result = (
        CollaborativeNoteDecisionResult(
            action=action,
            note=None,
            event=event,
        )
    )
    service_state.turn_service.error = AgentColTurnResponderError(
        "private responder failure",
        actions=(action,),
        collaborative_note_events=(event,),
        chat_turn_claim=effect_claim,
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "note-decision-failure-key-1"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Reject that note.",
            "collaborative_note_decision": decision.model_dump(mode="json"),
        },
    )

    assert response.status_code == 502
    assert response.json()["actions"] == [action.model_dump(mode="json")]
    assert response.json()["collaborative_note_events"] == [
        event.model_dump(mode="json")
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
        user_id: str,
        project_id: str,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        assert user_id == "user-1"
        assert project_id == "project-1"
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


@pytest.mark.asyncio
async def test_chat_does_not_update_working_state_when_completion_fails(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    claim = make_chat_turn_claim()
    service_state.database.chat_turn_result = claim
    service_state.database.working_state = make_working_state_snapshot()
    service_state.working_state_service.result = WorkingStateUpdateResult(
        update_required=True,
        snapshot=make_working_state_snapshot(
            current_goal="Persist only after completion succeeds."
        ),
    )
    service_state.database.complete_error = main.MemoryEngineError(
        "complete failed"
    )

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "private-owned-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "I want a deployment plan.",
        },
    )

    assert response.status_code == 500
    assert len(service_state.turn_service.calls) == 1
    assert service_state.working_state_service.calls == []
    assert service_state.database.working_state_save_calls == []


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


@pytest.mark.asyncio
async def test_chat_releases_claim_after_unexpected_turn_exception(
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
    service_state.turn_service.error = ValueError("private routing marker")

    response = await client.post(
        "/api/chat",
        headers={"Idempotency-Key": "unexpected-failure-key"},
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "New question",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Agent_Col response failed."}
    assert len(service_state.database.renew_calls) == 1
    assert len(service_state.turn_service.calls) == 1
    assert service_state.database.complete_calls == []
    assert len(service_state.database.release_calls) == 1
    assert service_state.database.release_calls[0][0] == renewed_claim
    assert service_state.database.release_calls[0][1].tzinfo is not None


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
async def test_chat_returns_clarification_on_responder_failure(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    clarification = make_memory_clarification_receipt()
    service_state.turn_service.error = AgentColTurnResponderError(
        "private provider failure",
        memory_clarifications=(clarification,),
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "Please remember that I prefer detailed guidance.",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Agent_Col response failed after a completed action.",
        "actions": [],
        "memory_proposals": [],
        "memory_clarifications": [clarification.model_dump(mode="json")],
    }


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
async def test_chat_logs_timeout_classification_without_private_content(
    client: httpx.AsyncClient,
    service_state: ServiceState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_state.turn_service.error = AgentColTurnTimeoutError(
        "private-provider-timeout-marker"
    )

    response = await client.post(
        "/api/chat",
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "private prompt marker",
        },
    )

    assert response.status_code == 504
    assert "Agent_Col chat turn timed out" in caplog.text
    assert "stage=turn" in caplog.text
    assert "completed_actions=0" in caplog.text
    for private_marker in (
        "private-provider-timeout-marker",
        "private-project",
        "private-session",
        "private-user",
        "private prompt marker",
    ):
        assert private_marker not in caplog.text


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
        *,
        user_id: str,
        project_id: str,
    ) -> list[dict[str, object]]:
        assert session_id == "session-1"
        assert limit == 20
        assert user_id == "user-1"
        assert project_id == "project-1"
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
