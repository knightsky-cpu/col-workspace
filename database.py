import logging
import math
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import NoReturn

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from google.cloud.firestore import (
    AsyncClient,
    AsyncCollectionReference,
    AsyncDocumentReference,
    AsyncTransaction,
)
from google.cloud.firestore_v1.field_path import FieldPath
from pydantic import ValidationError

from chat_turns import (
    CHAT_TURN_LEASE_DURATION,
    CHAT_TURN_SCHEMA_VERSION,
    ChatTurnClaim,
    ChatTurnConflictError,
    ChatTurnInProgressError,
    ChatTurnIds,
    ChatTurnOwnershipError,
    ChatTurnReplay,
    ChatTurnRequest,
    ChatTurnStateError,
    ChatSessionOwnershipError,
    derive_chat_turn_ids,
)
from memory_policy import (
    MEMORY_CATEGORY_ORDER,
    MEMORY_CATEGORY_ORDER_V2,
    ConfirmationChannel,
    MemoryCategory,
    MemoryCategoryV2,
    MemoryValue,
    validate_memory_value,
    validate_memory_value_for_policy,
)
from memory_clarifications import (
    MemoryClarificationEnvelope,
    MemoryClarificationReceipt,
    MemoryClarificationSelection,
    clarification_receipt,
    derive_memory_clarification_id,
    validate_memory_clarification_selection,
)
from memory_proposals import (
    PROPOSAL_ORIGIN_SCHEMA_VERSION,
    PROPOSAL_ORIGIN_SCHEMA_VERSION_V2,
    ProposalOriginIds,
    ProposalTurnLease,
    derive_proposal_origin_ids,
    derive_proposal_origin_ids_v2,
    parse_proposal_origin,
    proposal_origin_id_from_signal_id,
)
from schemas import (
    ARTIFACT_CONTRACT_VERSION,
    ActiveMemorySignal,
    AdaptationReceipt,
    AgentActionReceipt,
    ArtifactFeedbackCounts,
    ArtifactFeedbackDecisionRequest,
    ArtifactFeedbackReference,
    ArtifactFeedbackTargetKind,
    ArtifactReference,
    ChatMessageRecord,
    ChatResponse,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
    CollaborationProfile,
    CollaborationProfileV2,
    MemoryEvent,
    MemoryDecisionRequest,
    MemoryProposal,
    MemoryProposalReceipt,
    MemoryProposalReceiptV2,
    MemoryProposalV2,
    SingleFileArtifact,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceSummary,
    VersionedCollaborationProfile,
    VersionedMemoryProposal,
    VersionedMemoryProposalReceipt,
    parse_collaboration_profile,
    project_collaboration_profile_v2,
)


logger = logging.getLogger(__name__)


class MemoryEngineError(RuntimeError):
    """Raised when a Firestore memory operation fails."""


class MemoryProposalConflictError(RuntimeError):
    """Raised when an unexpired proposal owns a category slot."""


class MemoryProposalNotFoundError(RuntimeError):
    """Raised when a requested proposal slot does not exist."""


class MemoryProposalExpiredError(RuntimeError):
    """Raised when a requested pending proposal has expired."""


class MemoryProposalOriginConflictError(RuntimeError):
    """Raised when one source message selects a different proposal."""


class MemoryProposalStateError(RuntimeError):
    """Raised when guarded proposal state is internally inconsistent."""


class MemoryClarificationConflictError(RuntimeError):
    """Raised when a clarification retry differs from stored state."""


class MemoryClarificationStateError(RuntimeError):
    """Raised when durable clarification state is internally inconsistent."""


class MemorySignalAlreadyActiveError(RuntimeError):
    """Raised when a proposal would duplicate the active memory value."""


class MemorySignalNotFoundError(RuntimeError):
    """Raised when a governed memory signal cannot be revoked."""


class MemorySignalConflictError(RuntimeError):
    """Raised when stored signal state conflicts with a memory mutation."""


class MemoryEventCursorNotFoundError(RuntimeError):
    """Raised when a memory-event pagination cursor cannot be resolved."""


class BlueprintArtifactNotFoundError(RuntimeError):
    """Raised when a project-owned blueprint artifact does not exist."""


class BlueprintArtifactCursorNotFoundError(RuntimeError):
    """Raised when a blueprint pagination cursor cannot be resolved."""


class ArtifactNotFoundError(RuntimeError):
    """Raised when a project-owned generic artifact does not exist."""


class ArtifactCursorNotFoundError(RuntimeError):
    """Raised when generic artifact pagination cursor cannot be resolved."""


class BlueprintFeedbackCursorNotFoundError(RuntimeError):
    """Raised when a feedback pagination cursor cannot be resolved."""


class BlueprintFeedbackConflictError(RuntimeError):
    """Raised when a feedback identifier owns a different immutable event."""


class BlueprintFeedbackStateError(RuntimeError):
    """Raised when stored artifact feedback state is internally invalid."""


@dataclass(frozen=True, slots=True)
class MemoryApprovalResult:
    """Return the governed state created by a memory approval."""

    profile: CollaborationProfile
    event: MemoryEvent
    superseded_event: MemoryEvent | None = None


@dataclass(frozen=True, slots=True)
class MemoryRevocationResult:
    """Return the governed state created by a memory revocation."""

    profile: CollaborationProfile
    event: MemoryEvent


@dataclass(frozen=True, slots=True)
class MemoryDeletionResult:
    """Return the governed state after bounded hard deletion."""

    profile: CollaborationProfile
    artifacts_deleted: bool


@dataclass(frozen=True, slots=True)
class MemoryRejectionResult:
    """Return governed state after rejecting a pending proposal."""

    profile: CollaborationProfile
    proposal: MemoryProposal


@dataclass(frozen=True, slots=True)
class MemoryInspectionPage:
    """Return one bounded page of governed collaboration memory."""

    profile: CollaborationProfile
    unresolved_proposals: tuple[MemoryProposal, ...]
    events: tuple[MemoryEvent, ...]
    next_event_id: str | None


@dataclass(frozen=True, slots=True)
class BlueprintDocumentRecord:
    """One project-owned Firestore blueprint document."""

    artifact_id: str
    document: dict[str, object]


@dataclass(frozen=True, slots=True)
class BlueprintDocumentPage:
    """One bounded newest-first page of blueprint documents."""

    records: tuple[BlueprintDocumentRecord, ...]
    next_before: str | None


@dataclass(frozen=True, slots=True)
class ArtifactDocumentRecord:
    """One project-owned generic artifact document."""

    artifact_id: str
    document: dict[str, object]


@dataclass(frozen=True, slots=True)
class ArtifactDocumentPage:
    """One bounded newest-first page of generic artifact documents."""

    records: tuple[ArtifactDocumentRecord, ...]
    next_before: str | None


@dataclass(frozen=True, slots=True)
class BlueprintFeedbackDocumentRecord:
    """One immutable project-artifact feedback document."""

    feedback_id: str
    document: dict[str, object]
    superseded_by_feedback_id: str | None


@dataclass(frozen=True, slots=True)
class BlueprintFeedbackDocumentPage:
    """One bounded newest-first page of feedback documents."""

    records: tuple[BlueprintFeedbackDocumentRecord, ...]
    next_before: str | None


@dataclass(frozen=True, slots=True)
class ChatTurnArtifactEffectResult:
    """Return one atomically persisted chat-owned artifact effect."""

    claim: ChatTurnClaim
    artifact: ArtifactReference


@dataclass(frozen=True, slots=True)
class ChatTurnFeedbackEffectResult:
    """Return one atomically persisted chat-owned feedback effect."""

    claim: ChatTurnClaim
    action: AgentActionReceipt
    feedback: ArtifactFeedbackReference


class MemoryEngine:
    """Provide asynchronous persistence for chat messages and user profiles."""

    def __init__(self, client: AsyncClient | None = None) -> None:
        self._client = client if client is not None else AsyncClient()

    async def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        project_id: str,
        user_id: str,
    ) -> str:
        """Atomically persist a session update and a new chat message."""
        self._validate_string(session_id, "session_id")
        self._validate_string(role, "role")
        self._validate_string(text, "text")
        self._validate_string(project_id, "project_id")
        self._validate_string(user_id, "user_id")

        try:
            session_ref = self._client.collection("sessions").document(
                session_id
            )
            message_ref = session_ref.collection("messages").document()
            transaction = self._client.transaction()

            async def save_in_transaction(
                transaction: AsyncTransaction,
            ) -> None:
                session_snapshot = await session_ref.get(
                    transaction=transaction
                )
                session_document: dict[str, object] = {
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "last_message_preview": self._chat_preview(text),
                    "last_message_role": role,
                }
                if session_snapshot.exists:
                    self._validate_chat_session_owner(
                        session_snapshot.to_dict(),
                        user_id=user_id,
                        project_id=project_id,
                    )
                else:
                    session_document.update(
                        {
                            "project_id": project_id,
                            "user_id": user_id,
                        }
                    )
                transaction.set(
                    session_ref,
                    session_document,
                    merge=True,
                )
                transaction.set(
                    message_ref,
                    {
                        "role": role,
                        "text": text,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                    },
                )

            run_transaction = firestore.async_transactional(
                save_in_transaction
            )
            await run_transaction(transaction)
            return message_ref.id
        except (ChatSessionOwnershipError, ChatTurnStateError):
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("save_message", exc)

    async def list_chat_sessions(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int,
    ) -> ChatSessionListResponse:
        """Return bounded chat sessions visible to a local user/project."""
        self._validate_string(user_id, "user_id")
        self._validate_string(project_id, "project_id")
        self._validate_limit(limit, "limit", maximum=50)

        try:
            sessions_ref = self._client.collection("sessions")
            sessions: list[ChatSessionSummary] = []
            async for snapshot in sessions_ref.limit(200).stream():
                data = snapshot.to_dict()
                if not isinstance(data, Mapping):
                    continue
                if (
                    data.get("user_id") != user_id
                    or data.get("project_id") != project_id
                ):
                    continue
                sessions.append(
                    ChatSessionSummary(
                        session_id=snapshot.id,
                        project_id=project_id,
                        user_id=user_id,
                        updated_at=(
                            data.get("updated_at")
                            if isinstance(data.get("updated_at"), datetime)
                            else None
                        ),
                        last_message_preview=(
                            data.get("last_message_preview")
                            if isinstance(
                                data.get("last_message_preview"), str
                            )
                            else None
                        ),
                        last_message_role=(
                            data.get("last_message_role")
                            if data.get("last_message_role")
                            in {"user", "model"}
                            else None
                        ),
                    )
                )
            sessions.sort(
                key=lambda item: (
                    item.updated_at is not None,
                    (
                        item.updated_at
                        if item.updated_at is not None
                        else datetime.min
                    ),
                ),
                reverse=True,
            )
            return ChatSessionListResponse(sessions=sessions[:limit])
        except ValidationError as exc:
            raise ValueError("Stored chat session metadata is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_chat_sessions", exc)

    async def list_workspaces(
        self,
        *,
        user_id: str,
        default_workspace_id: str,
        default_display_name: str,
        limit: int,
    ) -> WorkspaceListResponse:
        """Return bounded workspace containers visible to one user."""
        self._validate_string(user_id, "user_id")
        self._validate_string(default_workspace_id, "default_workspace_id")
        self._validate_string(default_display_name, "default_display_name")
        self._validate_limit(limit, "limit", maximum=50)

        try:
            workspaces_ref = (
                self._client.collection("users")
                .document(user_id)
                .collection("workspaces")
            )
            workspaces: list[WorkspaceSummary] = []
            async for snapshot in workspaces_ref.limit(200).stream():
                data = snapshot.to_dict()
                if not isinstance(data, Mapping):
                    continue
                workspace_id = data.get("workspace_id")
                display_name = data.get("display_name")
                if (
                    workspace_id != snapshot.id
                    or not isinstance(display_name, str)
                ):
                    continue
                workspaces.append(
                    WorkspaceSummary(
                        workspace_id=snapshot.id,
                        display_name=display_name,
                        created_at=(
                            data.get("created_at")
                            if isinstance(data.get("created_at"), datetime)
                            else None
                        ),
                        updated_at=(
                            data.get("updated_at")
                            if isinstance(data.get("updated_at"), datetime)
                            else None
                        ),
                        is_default=bool(data.get("is_default", False)),
                    )
                )
            if not any(
                workspace.workspace_id == default_workspace_id
                for workspace in workspaces
            ):
                workspaces.append(
                    WorkspaceSummary(
                        workspace_id=default_workspace_id,
                        display_name=default_display_name,
                        is_default=True,
                    )
                )
            workspaces.sort(
                key=lambda item: (
                    not item.is_default,
                    item.display_name.casefold(),
                    item.workspace_id,
                )
            )
            return WorkspaceListResponse(workspaces=workspaces[:limit])
        except ValidationError as exc:
            raise ValueError("Stored workspace metadata is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_workspaces", exc)

    async def create_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: WorkspaceCreateRequest,
    ) -> WorkspaceSummary:
        """Persist one user-owned workspace container."""
        self._validate_string(user_id, "user_id")
        self._validate_string(workspace_id, "workspace_id")
        if not isinstance(request, WorkspaceCreateRequest):
            raise ValueError("request must be a WorkspaceCreateRequest.")

        try:
            user_ref = self._client.collection("users").document(user_id)
            workspace_ref = user_ref.collection("workspaces").document(
                workspace_id
            )
            batch = self._client.batch()
            batch.set(
                user_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.set(
                workspace_ref,
                {
                    "workspace_contract_version": "1.0",
                    "workspace_id": workspace_id,
                    "display_name": request.display_name,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "is_default": False,
                },
                merge=False,
            )
            await batch.commit()
            return WorkspaceSummary(
                workspace_id=workspace_id,
                display_name=request.display_name,
                is_default=False,
            )
        except GoogleAPIError as exc:
            self._raise_firestore_error("create_workspace", exc)

    async def get_chat_session_detail(
        self,
        *,
        user_id: str,
        project_id: str,
        session_id: str,
        limit: int,
    ) -> ChatSessionDetailResponse:
        """Return a bounded chronological transcript for one chat session."""
        self._validate_string(user_id, "user_id")
        self._validate_string(project_id, "project_id")
        self._validate_string(session_id, "session_id")
        self._validate_limit(limit, "limit", maximum=100)

        try:
            session_ref = self._client.collection("sessions").document(
                session_id
            )
            session_snapshot = await session_ref.get()
            session_data = session_snapshot.to_dict()
            if (
                not session_snapshot.exists
                or not isinstance(session_data, Mapping)
                or session_data.get("user_id") != user_id
                or session_data.get("project_id") != project_id
            ):
                return ChatSessionDetailResponse(
                    session_id=session_id,
                    project_id=project_id,
                    user_id=user_id,
                    messages=[],
                )
            messages_ref = session_ref.collection("messages")
            query = messages_ref.order_by(
                "timestamp",
                direction=firestore.Query.ASCENDING,
            ).limit(limit)
            messages: list[ChatMessageRecord] = []
            async for snapshot in query.stream():
                data = snapshot.to_dict()
                if not isinstance(data, Mapping):
                    continue
                role = data.get("role")
                text = data.get("text")
                if role not in {"user", "model"} or not isinstance(text, str):
                    continue
                timestamp = data.get("timestamp")
                messages.append(
                    ChatMessageRecord(
                        message_id=snapshot.id,
                        role=role,
                        text=text,
                        timestamp=(
                            timestamp
                            if isinstance(timestamp, datetime)
                            else None
                        ),
                    )
                )
            return ChatSessionDetailResponse(
                session_id=session_id,
                project_id=project_id,
                user_id=user_id,
                messages=messages,
            )
        except ValidationError as exc:
            raise ValueError("Stored chat session detail is invalid.") from exc
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_chat_session_detail", exc)

    async def claim_chat_turn(
        self,
        request: ChatTurnRequest,
        *,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ChatTurnClaim | ChatTurnReplay:
        """Atomically claim one durable logical chat turn."""
        if not isinstance(request, ChatTurnRequest):
            raise ValueError("request must be a ChatTurnRequest.")
        self._validate_memory_identifier(request.project_id, "project_id")
        self._validate_memory_identifier(request.session_id, "session_id")
        self._validate_memory_identifier(request.user_id, "user_id")
        self._validate_string(request.message, "message")
        if request.memory_decision is not None and not isinstance(
            request.memory_decision,
            MemoryDecisionRequest,
        ):
            raise ValueError(
                "memory_decision must be a MemoryDecisionRequest."
            )
        if request.artifact_feedback_decision is not None and not isinstance(
            request.artifact_feedback_decision,
            ArtifactFeedbackDecisionRequest,
        ):
            raise ValueError(
                "artifact_feedback_decision must be an "
                "ArtifactFeedbackDecisionRequest."
            )
        if (
            request.memory_decision is not None
            and request.artifact_feedback_decision is not None
        ):
            raise ValueError("structured decisions are mutually exclusive.")
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        ids = derive_chat_turn_ids(idempotency_key)
        owner_token = secrets.token_hex(16)
        lease_expires_at = observed_at + CHAT_TURN_LEASE_DURATION
        claim = ChatTurnClaim(
            request=request,
            ids=ids,
            owner_token=owner_token,
            lease_expires_at=lease_expires_at,
            resumed=False,
        )
        session_ref = self._client.collection("sessions").document(
            request.session_id
        )
        turn_ref = session_ref.collection("turns").document(ids.turn_id)
        messages_ref = session_ref.collection("messages")
        user_message_ref = messages_ref.document(ids.user_message_id)
        transaction = self._client.transaction()

        model_message_ref = messages_ref.document(ids.model_message_id)

        async def claim_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnClaim | ChatTurnReplay:
            session_snapshot = await session_ref.get(
                transaction=transaction
            )
            if session_snapshot.exists:
                self._validate_chat_session_owner(
                    session_snapshot.to_dict(),
                    user_id=request.user_id,
                    project_id=request.project_id,
                )
            turn_snapshot = await turn_ref.get(transaction=transaction)
            user_snapshot = await user_message_ref.get(
                transaction=transaction
            )
            if not session_snapshot.exists and turn_snapshot.exists:
                raise ChatTurnStateError(
                    "Stored chat turn has no parent session."
                )
            if turn_snapshot.exists != user_snapshot.exists:
                raise ChatTurnStateError(
                    "Stored chat turn has incomplete message state."
                )
            if turn_snapshot.exists:
                turn_data = turn_snapshot.to_dict()
                user_data = user_snapshot.to_dict()
                self._assert_chat_turn_request_matches(
                    request,
                    ids,
                    turn_data,
                    user_data,
                )
                if not isinstance(turn_data, Mapping):
                    raise ChatTurnStateError(
                        "Stored chat turn is invalid."
                    )
                status = turn_data.get("status")
                if status == "completed":
                    model_snapshot = await model_message_ref.get(
                        transaction=transaction
                    )
                    if not model_snapshot.exists:
                        raise ChatTurnStateError(
                            "Completed chat turn has no model message."
                        )
                    return self._chat_turn_replay(
                        turn_data,
                        model_snapshot.to_dict(),
                    )
                if status != "in_progress":
                    raise ChatTurnStateError(
                        "Stored chat turn status is invalid."
                    )
                stored_owner = turn_data.get("lease_owner")
                stored_expiry = turn_data.get("lease_expires_at")
                if (
                    not isinstance(stored_owner, str)
                    or not stored_owner
                    or not self._is_aware_datetime(stored_expiry)
                ):
                    raise ChatTurnStateError(
                        "Stored chat turn lease is invalid."
                    )
                if stored_expiry > observed_at:
                    retry_seconds = max(
                        1,
                        math.ceil(
                            (stored_expiry - observed_at).total_seconds()
                        ),
                    )
                    raise ChatTurnInProgressError(retry_seconds)
                (
                    precompleted_actions,
                    precompleted_proposals,
                    precompleted_artifacts,
                ) = (
                    self._chat_turn_effects(turn_data)
                )
                precompleted_feedback = (
                    self._chat_turn_feedback_effects(
                        turn_data,
                        precompleted_actions,
                    )
                )
                precompleted_clarifications = (
                    self._chat_turn_memory_clarifications(turn_data)
                )
                resumed_claim = ChatTurnClaim(
                    request=request,
                    ids=ids,
                    owner_token=owner_token,
                    lease_expires_at=lease_expires_at,
                    resumed=True,
                    precompleted_actions=precompleted_actions,
                    precompleted_memory_proposals=precompleted_proposals,
                    precompleted_memory_clarifications=(
                        precompleted_clarifications
                    ),
                    precompleted_artifacts=precompleted_artifacts,
                    precompleted_artifact_feedback=(
                        precompleted_feedback
                    ),
                )
                transaction.set(
                    turn_ref,
                    {
                        "lease_owner": owner_token,
                        "lease_expires_at": lease_expires_at,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
                return resumed_claim
            session_update: dict[str, object] = {
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_message_preview": self._chat_preview(
                    request.message
                ),
                "last_message_role": "user",
            }
            if not session_snapshot.exists:
                session_update.update(
                    {
                        "project_id": request.project_id,
                        "user_id": request.user_id,
                    }
                )
            transaction.set(session_ref, session_update, merge=True)
            feedback_decision = request.artifact_feedback_decision
            transaction.set(
                turn_ref,
                {
                    "schema_version": CHAT_TURN_SCHEMA_VERSION,
                    "status": "in_progress",
                    "project_id": request.project_id,
                    "user_id": request.user_id,
                    "memory_decision": (
                        request.memory_decision.model_dump(mode="json")
                        if request.memory_decision is not None
                        else None
                    ),
                    **(
                        {
                            "artifact_feedback_decision": (
                                feedback_decision.model_dump(mode="json")
                            )
                        }
                        if feedback_decision is not None
                        else {}
                    ),
                    "user_message_id": ids.user_message_id,
                    "model_message_id": ids.model_message_id,
                    "lease_owner": owner_token,
                    "lease_expires_at": lease_expires_at,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )
            transaction.set(
                user_message_ref,
                {
                    "role": "user",
                    "text": request.message,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                },
            )
            return claim

        run_transaction = firestore.async_transactional(
            claim_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error("claim_chat_turn", exc)

    async def renew_chat_turn_lease(
        self,
        claim: ChatTurnClaim,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        """Extend the lease held by the current chat-turn owner."""
        self._validate_chat_turn_claim(claim)
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        turn_ref = (
            self._client.collection("sessions")
            .document(claim.request.session_id)
            .collection("turns")
            .document(claim.ids.turn_id)
        )
        transaction = self._client.transaction()
        lease_expires_at = observed_at + CHAT_TURN_LEASE_DURATION

        async def renew_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnClaim:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            turn_data = turn_snapshot.to_dict()
            if (
                not turn_snapshot.exists
                or not isinstance(turn_data, Mapping)
                or turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(
                    turn_data.get("lease_expires_at")
                )
                or turn_data["lease_expires_at"] <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn lease cannot be renewed."
                )
            transaction.set(
                turn_ref,
                {
                    "lease_expires_at": lease_expires_at,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return replace(claim, lease_expires_at=lease_expires_at)

        run_transaction = firestore.async_transactional(
            renew_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error("renew_chat_turn_lease", exc)

    async def record_chat_turn_decision_action(
        self,
        claim: ChatTurnClaim,
        action: AgentActionReceipt,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        """Persist one owned structured memory-decision action receipt."""
        self._validate_chat_turn_claim(claim)
        if not isinstance(action, AgentActionReceipt):
            raise ValueError("action must be an AgentActionReceipt.")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        decision = claim.request.memory_decision
        if decision is None:
            raise ValueError("claim must contain a memory decision.")
        expected_action_name = (
            "approve_memory_signal"
            if decision.decision == "approve"
            else "reject_memory_signal"
        )
        if action.action_name != expected_action_name:
            raise ValueError("action does not match the memory decision.")
        turn_ref = (
            self._client.collection("sessions")
            .document(claim.request.session_id)
            .collection("turns")
            .document(claim.ids.turn_id)
        )
        transaction = self._client.transaction()

        async def record_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnClaim:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            turn_data = turn_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data,
                Mapping,
            ):
                raise ChatTurnStateError("Stored chat turn is invalid.")
            self._assert_chat_turn_claim_matches_document(claim, turn_data)
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
                or stored_expiry <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn cannot record a decision action."
                )
            (
                stored_actions,
                stored_proposals,
                stored_artifacts,
            ) = self._chat_turn_effects(turn_data)
            decision_actions = tuple(
                item
                for item in stored_actions
                if item.action_name
                in {"approve_memory_signal", "reject_memory_signal"}
            )
            if decision_actions and decision_actions != (action,):
                raise ChatTurnStateError(
                    "Stored chat turn has a conflicting decision action."
                )
            actions = stored_actions
            if not decision_actions:
                actions = (*stored_actions, action)
                transaction.set(
                    turn_ref,
                    {
                        "actions": [
                            item.model_dump(mode="python")
                            for item in actions
                        ],
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
            return replace(
                claim,
                precompleted_actions=actions,
                precompleted_memory_proposals=stored_proposals,
                precompleted_artifacts=stored_artifacts,
            )

        run_transaction = firestore.async_transactional(record_in_transaction)
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "record_chat_turn_decision_action",
                exc,
            )

    async def release_chat_turn(
        self,
        claim: ChatTurnClaim,
        *,
        observed_at: datetime,
    ) -> ChatTurnClaim:
        """Expire an owned lease and return its completed turn effects."""
        self._validate_chat_turn_claim(claim)
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        turn_ref = (
            self._client.collection("sessions")
            .document(claim.request.session_id)
            .collection("turns")
            .document(claim.ids.turn_id)
        )
        transaction = self._client.transaction()

        async def release_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnClaim:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            turn_data = turn_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data, Mapping
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn lease cannot be released."
                )
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn lease cannot be released."
                )
            (
                stored_actions,
                stored_proposals,
                stored_artifacts,
            ) = self._chat_turn_effects(turn_data)
            stored_feedback = self._chat_turn_feedback_effects(
                turn_data,
                stored_actions,
            )
            stored_clarifications = (
                self._chat_turn_memory_clarifications(turn_data)
            )
            released_claim = replace(
                claim,
                lease_expires_at=min(stored_expiry, observed_at),
                precompleted_actions=stored_actions,
                precompleted_memory_proposals=stored_proposals,
                precompleted_memory_clarifications=stored_clarifications,
                precompleted_artifacts=stored_artifacts,
                precompleted_artifact_feedback=stored_feedback,
            )
            if stored_expiry <= observed_at:
                return released_claim
            transaction.set(
                turn_ref,
                {
                    "lease_expires_at": observed_at,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return released_claim

        run_transaction = firestore.async_transactional(
            release_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error("release_chat_turn", exc)

    async def record_chat_turn_blueprint_effect(
        self,
        claim: ChatTurnClaim,
        *,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
        display_label: str,
        observed_at: datetime,
        adaptations: tuple[AdaptationReceipt, ...] = (),
    ) -> ChatTurnArtifactEffectResult:
        """Atomically persist one blueprint and its owned turn receipts."""
        self._validate_chat_turn_claim(claim)
        self._validate_string(model_name, "model_name")
        self._validate_string(schema_version, "schema_version")
        self._validate_blueprint(blueprint)
        adaptation_documents = self._adaptation_receipt_documents(
            adaptations
        )
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if (
            claim.request.memory_decision is not None
            or claim.precompleted_memory_proposals
        ):
            raise ValueError(
                "artifact turns cannot contain governed-memory decisions."
            )
        if (
            claim.request.artifact_feedback_decision is not None
            or claim.precompleted_artifact_feedback
        ):
            raise ValueError(
                "artifact turns cannot contain artifact-feedback decisions."
            )

        artifact = ArtifactReference(
            artifact_type="synthesis_blueprint",
            project_id=claim.request.project_id,
            artifact_id=f"blueprint--{claim.ids.turn_id}",
            schema_version=schema_version,
            display_label=display_label,
        )
        action = AgentActionReceipt(
            action_name="synthesize_project",
            status="completed",
        )
        session_ref = self._client.collection("sessions").document(
            claim.request.session_id
        )
        turn_ref = session_ref.collection("turns").document(
            claim.ids.turn_id
        )
        project_ref = self._client.collection("projects").document(
            claim.request.project_id
        )
        blueprint_ref = project_ref.collection("blueprints").document(
            artifact.artifact_id
        )
        transaction = self._client.transaction()

        async def record_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnArtifactEffectResult:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            blueprint_snapshot = await blueprint_ref.get(
                transaction=transaction
            )
            turn_data = turn_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data,
                Mapping,
            ):
                raise ChatTurnStateError("Stored chat turn is invalid.")
            self._assert_chat_turn_claim_matches_document(claim, turn_data)
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
                or stored_expiry <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn cannot record an artifact effect."
                )
            (
                stored_actions,
                stored_proposals,
                stored_artifacts,
            ) = self._chat_turn_effects(turn_data)
            if stored_proposals:
                raise ChatTurnStateError(
                    "Stored artifact turn contains a memory proposal."
                )
            if stored_artifacts:
                if not blueprint_snapshot.exists:
                    raise ChatTurnStateError(
                        "Stored artifact effect has no blueprint document."
                    )
                stored_artifact = stored_artifacts[0]
                self._assert_chat_turn_blueprint_document_matches(
                    claim,
                    stored_artifact,
                    blueprint_snapshot.to_dict(),
                    adaptation_documents,
                )
                return ChatTurnArtifactEffectResult(
                    claim=replace(
                        claim,
                        precompleted_actions=stored_actions,
                        precompleted_memory_proposals=stored_proposals,
                        precompleted_artifacts=stored_artifacts,
                    ),
                    artifact=stored_artifact,
                )
            if blueprint_snapshot.exists:
                raise ChatTurnStateError(
                    "Blueprint document has no stored turn effect."
                )

            actions = (*stored_actions, action)
            artifacts = (artifact,)
            transaction.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            transaction.set(
                blueprint_ref,
                {
                    "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
                    "artifact_type": "synthesis_blueprint",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "originating_session_id": claim.request.session_id,
                    "originating_turn_id": claim.ids.turn_id,
                    "user_id": claim.request.user_id,
                    "model_name": model_name,
                    "schema_version": schema_version,
                    "parent_artifact_id": None,
                    "feedback_counts": {
                        "accepted": 0,
                        "rejected": 0,
                        "edited": 0,
                    },
                    "adaptation_receipts": adaptation_documents,
                    "applied_feedback_ids": [],
                    "blueprint": blueprint,
                },
            )
            transaction.set(
                turn_ref,
                {
                    "actions": [
                        item.model_dump(mode="python") for item in actions
                    ],
                    "artifacts": [
                        item.model_dump(mode="python") for item in artifacts
                    ],
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return ChatTurnArtifactEffectResult(
                claim=replace(
                    claim,
                    precompleted_actions=actions,
                    precompleted_artifacts=artifacts,
                ),
                artifact=artifact,
            )

        run_transaction = firestore.async_transactional(
            record_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "record_chat_turn_blueprint_effect",
                exc,
            )

    async def record_chat_turn_single_file_artifact_effect(
        self,
        claim: ChatTurnClaim,
        *,
        model_name: str,
        artifact: dict[str, object],
        display_label: str,
        observed_at: datetime,
    ) -> ChatTurnArtifactEffectResult:
        """Atomically persist one single-file artifact and turn receipts."""
        self._validate_chat_turn_claim(claim)
        self._validate_string(model_name, "model_name")
        validated_artifact = SingleFileArtifact.model_validate(artifact)
        self._validate_string(display_label, "display_label")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if (
            claim.request.memory_decision is not None
            or claim.precompleted_memory_proposals
        ):
            raise ValueError(
                "artifact turns cannot contain governed-memory decisions."
            )
        if (
            claim.request.artifact_feedback_decision is not None
            or claim.precompleted_artifact_feedback
        ):
            raise ValueError(
                "artifact turns cannot contain artifact-feedback decisions."
            )

        artifact_ref = ArtifactReference(
            artifact_type="single_file_artifact",
            project_id=claim.request.project_id,
            artifact_id=f"artifact--{claim.ids.turn_id}",
            schema_version="1.0",
            display_label=display_label,
        )
        action = AgentActionReceipt(
            action_name="create_artifact",
            status="completed",
        )
        document = validated_artifact.model_dump(mode="python")
        session_ref = self._client.collection("sessions").document(
            claim.request.session_id
        )
        turn_ref = session_ref.collection("turns").document(
            claim.ids.turn_id
        )
        project_ref = self._client.collection("projects").document(
            claim.request.project_id
        )
        stored_artifact_ref = project_ref.collection("artifacts").document(
            artifact_ref.artifact_id
        )
        transaction = self._client.transaction()

        async def record_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnArtifactEffectResult:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            artifact_snapshot = await stored_artifact_ref.get(
                transaction=transaction
            )
            turn_data = turn_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data,
                Mapping,
            ):
                raise ChatTurnStateError("Stored chat turn is invalid.")
            self._assert_chat_turn_claim_matches_document(claim, turn_data)
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
                or stored_expiry <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn cannot record an artifact effect."
                )
            (
                stored_actions,
                stored_proposals,
                stored_artifacts,
            ) = self._chat_turn_effects(turn_data)
            if stored_proposals:
                raise ChatTurnStateError(
                    "Stored artifact turn contains a memory proposal."
                )
            if stored_artifacts:
                if not artifact_snapshot.exists:
                    raise ChatTurnStateError(
                        "Stored artifact effect has no artifact document."
                    )
                stored_artifact = stored_artifacts[0]
                self._assert_chat_turn_single_file_document_matches(
                    claim,
                    stored_artifact,
                    artifact_snapshot.to_dict(),
                )
                return ChatTurnArtifactEffectResult(
                    claim=replace(
                        claim,
                        precompleted_actions=stored_actions,
                        precompleted_memory_proposals=stored_proposals,
                        precompleted_artifacts=stored_artifacts,
                    ),
                    artifact=stored_artifact,
                )
            if artifact_snapshot.exists:
                raise ChatTurnStateError(
                    "Artifact document has no stored turn effect."
                )

            actions = (*stored_actions, action)
            artifacts = (artifact_ref,)
            transaction.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            transaction.set(
                stored_artifact_ref,
                {
                    "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
                    "artifact_type": "single_file_artifact",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "originating_session_id": claim.request.session_id,
                    "originating_turn_id": claim.ids.turn_id,
                    "user_id": claim.request.user_id,
                    "model_name": model_name,
                    "schema_version": "1.0",
                    "display_label": display_label,
                    "lifecycle_status": "active",
                    "filename": validated_artifact.filename,
                    "artifact_family": validated_artifact.artifact_family,
                    "format": validated_artifact.format,
                    "byte_size": len(
                        validated_artifact.content.encode("utf-8")
                    ),
                    "content": validated_artifact.content,
                    "summary": validated_artifact.summary,
                },
            )
            transaction.set(
                turn_ref,
                {
                    "actions": [
                        item.model_dump(mode="python") for item in actions
                    ],
                    "artifacts": [
                        item.model_dump(mode="python") for item in artifacts
                    ],
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return ChatTurnArtifactEffectResult(
                claim=replace(
                    claim,
                    precompleted_actions=actions,
                    precompleted_artifacts=artifacts,
                ),
                artifact=artifact_ref,
            )

        run_transaction = firestore.async_transactional(
            record_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "record_chat_turn_single_file_artifact_effect",
                exc,
            )

    async def record_chat_turn_artifact_feedback_effect(
        self,
        claim: ChatTurnClaim,
        *,
        target_kind: ArtifactFeedbackTargetKind,
        observed_at: datetime,
    ) -> ChatTurnFeedbackEffectResult:
        """Atomically persist artifact feedback and its turn receipts."""
        self._validate_chat_turn_claim(claim)
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        request = claim.request.artifact_feedback_decision
        if request is None or claim.request.memory_decision is not None:
            raise ValueError(
                "claim must contain one artifact feedback decision."
            )
        feedback_id = f"feedback--{claim.ids.turn_id}"
        action = AgentActionReceipt(
            action_name="record_blueprint_feedback",
            status="completed",
        )
        feedback = ArtifactFeedbackReference(
            feedback_id=feedback_id,
            artifact_id=request.artifact_id,
            target_id=request.target_id,
            target_kind=target_kind,
            decision=request.decision,
            schema_version=request.expected_schema_version,
            created_at=observed_at,
        )
        session_ref = self._client.collection("sessions").document(
            claim.request.session_id
        )
        turn_ref = session_ref.collection("turns").document(
            claim.ids.turn_id
        )
        project_ref = self._client.collection("projects").document(
            claim.request.project_id
        )
        blueprint_ref = project_ref.collection("blueprints").document(
            request.artifact_id
        )
        feedback_ref = blueprint_ref.collection("feedback").document(
            feedback_id
        )
        supersedes_feedback_id = request.supersedes_feedback_id
        prior_feedback_ref = (
            blueprint_ref.collection("feedback").document(
                supersedes_feedback_id
            )
            if supersedes_feedback_id is not None
            else None
        )
        supersession_ref = (
            blueprint_ref.collection("feedback_supersessions").document(
                supersedes_feedback_id
            )
            if supersedes_feedback_id is not None
            else None
        )
        transaction = self._client.transaction()
        feedback_document = {
            "feedback_contract_version": "1.0",
            "feedback_id": feedback_id,
            "artifact_id": request.artifact_id,
            "target_id": request.target_id,
            "target_kind": target_kind,
            "decision": request.decision,
            "feedback_text": request.feedback_text,
            "correction_text": request.correction_text,
            "originating_session_id": claim.request.session_id,
            "source_message_id": claim.ids.user_message_id,
            "originating_turn_id": claim.ids.turn_id,
            "user_id": claim.request.user_id,
            "schema_version": request.expected_schema_version,
            "created_at": observed_at,
            "status": "active",
            "supersedes_feedback_id": supersedes_feedback_id,
        }
        supersession_document = (
            {
                "supersession_contract_version": "1.0",
                "supersedes_feedback_id": supersedes_feedback_id,
                "superseded_by_feedback_id": feedback_id,
                "created_at": observed_at,
            }
            if supersedes_feedback_id is not None
            else None
        )

        async def record_in_transaction(
            transaction: AsyncTransaction,
        ) -> ChatTurnFeedbackEffectResult:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            blueprint_snapshot = await blueprint_ref.get(
                transaction=transaction
            )
            feedback_snapshot = await feedback_ref.get(
                transaction=transaction
            )
            prior_feedback_snapshot = (
                await prior_feedback_ref.get(transaction=transaction)
                if prior_feedback_ref is not None
                else None
            )
            supersession_snapshot = (
                await supersession_ref.get(transaction=transaction)
                if supersession_ref is not None
                else None
            )
            turn_data = turn_snapshot.to_dict()
            blueprint_document = blueprint_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data,
                Mapping,
            ):
                raise ChatTurnStateError("Stored chat turn is invalid.")
            self._assert_chat_turn_claim_matches_document(claim, turn_data)
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
                or stored_expiry <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn cannot record a feedback effect."
                )
            if not blueprint_snapshot.exists or not isinstance(
                blueprint_document,
                Mapping,
            ):
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            if blueprint_document.get("user_id") != claim.request.user_id:
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            if (
                blueprint_document.get("artifact_contract_version")
                != ARTIFACT_CONTRACT_VERSION
                or blueprint_document.get("artifact_type")
                != "synthesis_blueprint"
            ):
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback state is invalid."
                )
            if (
                blueprint_document.get("schema_version")
                != request.expected_schema_version
            ):
                raise BlueprintFeedbackConflictError(
                    "Blueprint schema conflicts with feedback command."
                )
            try:
                counts = ArtifactFeedbackCounts.model_validate(
                    blueprint_document.get("feedback_counts", {})
                )
            except ValidationError as exc:
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback state is invalid."
                ) from exc
            prior_decision = None
            if supersedes_feedback_id is not None:
                prior_document = (
                    prior_feedback_snapshot.to_dict()
                    if prior_feedback_snapshot is not None
                    else None
                )
                if (
                    prior_feedback_snapshot is None
                    or not prior_feedback_snapshot.exists
                    or not isinstance(prior_document, Mapping)
                    or prior_document.get("feedback_contract_version")
                    != "1.0"
                    or prior_document.get("feedback_id")
                    != supersedes_feedback_id
                    or prior_document.get("artifact_id")
                    != request.artifact_id
                    or prior_document.get("target_id") != request.target_id
                    or prior_document.get("target_kind") != target_kind
                    or prior_document.get("user_id") != claim.request.user_id
                    or prior_document.get("schema_version")
                    != request.expected_schema_version
                    or prior_document.get("status") != "active"
                    or not self._is_aware_datetime(
                        prior_document.get("created_at")
                    )
                    or prior_document.get("created_at") > observed_at
                ):
                    raise BlueprintFeedbackConflictError(
                        "Prior feedback cannot be superseded."
                    )
                prior_decision = prior_document.get("decision")
                if prior_decision not in {
                    "accepted",
                    "rejected",
                    "edited",
                }:
                    raise BlueprintFeedbackStateError(
                        "Stored prior feedback decision is invalid."
                    )
                if (
                    supersession_snapshot is not None
                    and supersession_snapshot.exists
                ):
                    existing_link = supersession_snapshot.to_dict()
                    existing_link_created_at = (
                        existing_link.get("created_at")
                        if isinstance(existing_link, Mapping)
                        else None
                    )
                    stable_existing_link = (
                        dict(existing_link)
                        if isinstance(existing_link, Mapping)
                        else {}
                    )
                    stable_existing_link.pop("created_at", None)
                    stable_supersession_document = dict(
                        supersession_document
                    )
                    stable_supersession_document.pop("created_at", None)
                    if (
                        not isinstance(existing_link, Mapping)
                        or not self._is_aware_datetime(
                            existing_link_created_at
                        )
                        or existing_link_created_at > observed_at
                        or stable_existing_link
                        != stable_supersession_document
                    ):
                        raise BlueprintFeedbackConflictError(
                            "Prior feedback is already superseded."
                        )
                if feedback_snapshot.exists != supersession_snapshot.exists:
                    raise BlueprintFeedbackStateError(
                        "Stored feedback supersession is incomplete."
                    )
            stored_actions, stored_proposals, stored_artifacts = (
                self._chat_turn_effects(turn_data)
            )
            if stored_proposals or stored_artifacts:
                raise ChatTurnStateError(
                    "Stored feedback turn contains another durable effect."
                )
            stored_feedback = self._chat_turn_feedback_effects(
                turn_data,
                stored_actions,
            )
            if stored_feedback:
                existing_document = feedback_snapshot.to_dict()
                existing_created_at = (
                    existing_document.get("created_at")
                    if isinstance(existing_document, Mapping)
                    else None
                )
                if (
                    not feedback_snapshot.exists
                    or not isinstance(existing_document, Mapping)
                    or not self._is_aware_datetime(existing_created_at)
                    or existing_created_at > observed_at
                ):
                    raise ChatTurnStateError(
                        "Stored feedback turn event is invalid."
                    )
                stable_existing_document = dict(existing_document)
                stable_existing_document.pop("created_at", None)
                stable_feedback_document = dict(feedback_document)
                stable_feedback_document.pop("created_at", None)
                original_feedback = feedback.model_copy(
                    update={"created_at": existing_created_at}
                )
                if (
                    stable_existing_document != stable_feedback_document
                    or stored_feedback != (original_feedback,)
                ):
                    raise ChatTurnStateError(
                        "Stored feedback turn event is invalid."
                    )
                return ChatTurnFeedbackEffectResult(
                    claim=replace(
                        claim,
                        precompleted_actions=stored_actions,
                        precompleted_memory_proposals=stored_proposals,
                        precompleted_artifacts=stored_artifacts,
                        precompleted_artifact_feedback=stored_feedback,
                    ),
                    action=action,
                    feedback=original_feedback,
                )
            if feedback_snapshot.exists:
                raise ChatTurnStateError(
                    "Feedback event has no stored turn effect."
                )

            actions = (*stored_actions, action)
            count_values = counts.model_dump()
            if prior_decision is not None:
                if count_values[prior_decision] < 1:
                    raise BlueprintFeedbackStateError(
                        "Stored feedback counts cannot be superseded."
                    )
                count_values[prior_decision] -= 1
            count_values[request.decision] += 1
            updated_counts = ArtifactFeedbackCounts.model_validate(
                count_values
            )
            transaction.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            transaction.set(feedback_ref, feedback_document)
            if supersession_ref is not None:
                transaction.set(
                    supersession_ref,
                    supersession_document,
                )
            transaction.set(
                blueprint_ref,
                {"feedback_counts": updated_counts.model_dump()},
                merge=True,
            )
            transaction.set(
                turn_ref,
                {
                    "actions": [
                        item.model_dump(mode="python") for item in actions
                    ],
                    "artifact_feedback": [
                        feedback.model_dump(mode="python")
                    ],
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return ChatTurnFeedbackEffectResult(
                claim=replace(
                    claim,
                    precompleted_actions=actions,
                    precompleted_artifact_feedback=(feedback,),
                ),
                action=action,
                feedback=feedback,
            )

        run_transaction = firestore.async_transactional(
            record_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "record_chat_turn_artifact_feedback_effect",
                exc,
            )

    def _assert_chat_turn_blueprint_document_matches(
        self,
        claim: ChatTurnClaim,
        artifact: ArtifactReference,
        document: object,
        adaptation_documents: list[dict[str, object]],
    ) -> None:
        if not isinstance(document, Mapping):
            raise ChatTurnStateError(
                "Stored blueprint document is invalid."
            )
        blueprint = document.get("blueprint")
        if (
            document.get("artifact_contract_version")
            != ARTIFACT_CONTRACT_VERSION
            or document.get("artifact_type") != artifact.artifact_type
            or document.get("originating_session_id")
            != claim.request.session_id
            or document.get("originating_turn_id") != claim.ids.turn_id
            or document.get("user_id") != claim.request.user_id
            or document.get("schema_version") != artifact.schema_version
            or not self._is_aware_datetime(document.get("created_at"))
            or not isinstance(document.get("model_name"), str)
            or not document.get("model_name")
            or not isinstance(blueprint, Mapping)
            or not blueprint
        ):
            raise ChatTurnStateError(
                "Stored blueprint document does not match its turn effect."
            )
        if document.get("adaptation_receipts") != adaptation_documents:
            raise ChatTurnStateError(
                "Stored blueprint adaptation receipts conflict with this "
                "turn effect."
            )

    def _assert_chat_turn_single_file_document_matches(
        self,
        claim: ChatTurnClaim,
        artifact: ArtifactReference,
        document: object,
    ) -> None:
        if not isinstance(document, Mapping):
            raise ChatTurnStateError("Stored artifact document is invalid.")
        if (
            document.get("artifact_contract_version")
            != ARTIFACT_CONTRACT_VERSION
            or document.get("artifact_type") != artifact.artifact_type
            or document.get("originating_session_id")
            != claim.request.session_id
            or document.get("originating_turn_id") != claim.ids.turn_id
            or document.get("user_id") != claim.request.user_id
            or document.get("schema_version") != artifact.schema_version
            or document.get("display_label") != artifact.display_label
            or not self._is_aware_datetime(document.get("created_at"))
            or not isinstance(document.get("model_name"), str)
            or not document.get("model_name")
        ):
            raise ChatTurnStateError(
                "Stored artifact document does not match its turn effect."
            )
        try:
            SingleFileArtifact.model_validate(
                {
                    "artifact_family": document.get("artifact_family"),
                    "format": document.get("format"),
                    "filename": document.get("filename"),
                    "content": document.get("content"),
                    "summary": document.get("summary"),
                }
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored artifact document does not match its turn effect."
            ) from exc

    async def complete_chat_turn(
        self,
        claim: ChatTurnClaim,
        response: ChatResponse,
        *,
        observed_at: datetime,
    ) -> None:
        """Atomically persist a model response and complete its chat turn."""
        self._validate_chat_turn_claim(claim)
        if not isinstance(response, ChatResponse):
            raise ValueError("response must be a ChatResponse.")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        session_ref = self._client.collection("sessions").document(
            claim.request.session_id
        )
        turn_ref = session_ref.collection("turns").document(
            claim.ids.turn_id
        )
        model_message_ref = session_ref.collection("messages").document(
            claim.ids.model_message_id
        )
        transaction = self._client.transaction()

        async def complete_in_transaction(
            transaction: AsyncTransaction,
        ) -> None:
            turn_snapshot = await turn_ref.get(transaction=transaction)
            model_snapshot = await model_message_ref.get(
                transaction=transaction
            )
            turn_data = turn_snapshot.to_dict()
            if not turn_snapshot.exists or not isinstance(
                turn_data, Mapping
            ):
                raise ChatTurnStateError("Stored chat turn is invalid.")
            self._assert_chat_turn_claim_matches_document(claim, turn_data)
            stored_expiry = turn_data.get("lease_expires_at")
            if (
                turn_data.get("status") != "in_progress"
                or turn_data.get("lease_owner") != claim.owner_token
                or not self._is_aware_datetime(stored_expiry)
                or stored_expiry <= observed_at
            ):
                raise ChatTurnOwnershipError(
                    "Stored chat turn lease cannot be completed."
                )
            if model_snapshot.exists:
                raise ChatTurnStateError(
                    "Stored chat turn already has a model message."
                )
            self._assert_chat_turn_response_preserves_effects(
                turn_data,
                response,
            )
            receipts = response.model_dump(
                mode="json",
                exclude={"response"},
            )
            transaction.set(
                session_ref,
                {
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "last_message_preview": self._chat_preview(
                        response.response
                    ),
                    "last_message_role": "model",
                    "last_completed_turn_id": claim.ids.turn_id,
                },
                merge=True,
            )
            transaction.set(
                model_message_ref,
                {
                    "role": "model",
                    "text": response.response,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                },
            )
            transaction.set(
                turn_ref,
                {
                    "status": "completed",
                    **receipts,
                    "completed_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "lease_owner": firestore.DELETE_FIELD,
                    "lease_expires_at": firestore.DELETE_FIELD,
                },
                merge=True,
            )

        run_transaction = firestore.async_transactional(
            complete_in_transaction
        )
        try:
            await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error("complete_chat_turn", exc)

    def _assert_chat_turn_request_matches(
        self,
        request: ChatTurnRequest,
        ids: ChatTurnIds,
        turn_data: object,
        user_message_data: object,
    ) -> None:
        if not isinstance(turn_data, Mapping) or not isinstance(
            user_message_data, Mapping
        ):
            raise ChatTurnStateError("Stored chat turn is invalid.")
        if any(
            field in turn_data
            for field in ("message", "text", "response")
        ):
            raise ChatTurnStateError(
                "Stored chat turn contains prohibited content."
            )
        if (
            turn_data.get("schema_version") != CHAT_TURN_SCHEMA_VERSION
            or turn_data.get("user_message_id") != ids.user_message_id
            or turn_data.get("model_message_id") != ids.model_message_id
            or not self._is_aware_datetime(turn_data.get("created_at"))
            or not self._is_aware_datetime(turn_data.get("updated_at"))
        ):
            raise ChatTurnStateError("Stored chat turn metadata is invalid.")
        expected_decision = (
            request.memory_decision.model_dump(mode="json")
            if request.memory_decision is not None
            else None
        )
        expected_feedback_decision = (
            request.artifact_feedback_decision.model_dump(mode="json")
            if request.artifact_feedback_decision is not None
            else None
        )
        if (
            turn_data.get("project_id") != request.project_id
            or turn_data.get("user_id") != request.user_id
            or turn_data.get("memory_decision") != expected_decision
            or turn_data.get("artifact_feedback_decision")
            != expected_feedback_decision
        ):
            raise ChatTurnConflictError(
                "Idempotency key conflicts with a different chat request."
            )
        if (
            set(user_message_data)
            != {"role", "text", "timestamp"}
            or user_message_data.get("role") != "user"
            or not self._is_aware_datetime(
                user_message_data.get("timestamp")
            )
        ):
            raise ChatTurnStateError("Stored user message is invalid.")
        if user_message_data.get("text") != request.message:
            raise ChatTurnConflictError(
                "Idempotency key conflicts with a different chat request."
            )

    @staticmethod
    def _validate_chat_session_owner(
        document: object,
        *,
        user_id: str,
        project_id: str,
    ) -> None:
        if not isinstance(document, Mapping):
            raise ChatTurnStateError("Stored chat session is invalid.")
        stored_user_id = document.get("user_id")
        stored_project_id = document.get("project_id")
        if (
            not isinstance(stored_user_id, str)
            or not stored_user_id
            or not isinstance(stored_project_id, str)
            or not stored_project_id
        ):
            raise ChatTurnStateError(
                "Stored chat session ownership is invalid."
            )
        if stored_user_id != user_id or stored_project_id != project_id:
            raise ChatSessionOwnershipError(
                "Chat session is unavailable."
            )

    def _validate_chat_turn_claim(self, claim: object) -> None:
        if not isinstance(claim, ChatTurnClaim):
            raise ValueError("claim must be a valid ChatTurnClaim.")
        request = claim.request
        if not isinstance(request, ChatTurnRequest):
            raise ValueError("claim request is invalid.")
        self._validate_memory_identifier(request.project_id, "project_id")
        self._validate_memory_identifier(request.session_id, "session_id")
        self._validate_memory_identifier(request.user_id, "user_id")
        self._validate_string(request.message, "message")
        if request.memory_decision is not None and not isinstance(
            request.memory_decision,
            MemoryDecisionRequest,
        ):
            raise ValueError("claim memory_decision is invalid.")
        if request.artifact_feedback_decision is not None and not isinstance(
            request.artifact_feedback_decision,
            ArtifactFeedbackDecisionRequest,
        ):
            raise ValueError("claim artifact_feedback_decision is invalid.")
        if (
            request.memory_decision is not None
            and request.artifact_feedback_decision is not None
        ):
            raise ValueError("claim structured decisions are invalid.")
        turn_id = claim.ids.turn_id
        if not isinstance(turn_id, str) or re.fullmatch(
            r"[a-f0-9]{64}", turn_id
        ) is None:
            raise ValueError("claim turn ID is invalid.")
        if (
            claim.ids.user_message_id != f"turn--{turn_id}--user"
            or claim.ids.model_message_id != f"turn--{turn_id}--model"
            or not isinstance(claim.owner_token, str)
            or not claim.owner_token
            or not self._is_aware_datetime(claim.lease_expires_at)
            or not isinstance(claim.resumed, bool)
        ):
            raise ValueError("claim metadata is invalid.")
        actions = claim.precompleted_actions
        proposals = claim.precompleted_memory_proposals
        clarifications = claim.precompleted_memory_clarifications
        artifacts = claim.precompleted_artifacts
        feedback = claim.precompleted_artifact_feedback
        if (
            not isinstance(actions, tuple)
            or not all(
                isinstance(action, AgentActionReceipt) for action in actions
            )
            or not isinstance(proposals, tuple)
            or not all(
                isinstance(
                    proposal,
                    (MemoryProposalReceipt, MemoryProposalReceiptV2),
                )
                for proposal in proposals
            )
            or not isinstance(artifacts, tuple)
            or not all(
                isinstance(artifact, ArtifactReference)
                for artifact in artifacts
            )
            or not isinstance(feedback, tuple)
            or not all(
                isinstance(item, ArtifactFeedbackReference)
                for item in feedback
            )
            or not isinstance(clarifications, tuple)
            or not all(
                isinstance(item, MemoryClarificationReceipt)
                for item in clarifications
            )
        ):
            raise ValueError("claim effects are invalid.")
        proposal_actions = tuple(
            action
            for action in actions
            if action.action_name == "propose_memory_signal"
        )
        if (
            len(proposals) > 1
            or len(clarifications) > 1
            or bool(proposals) and bool(clarifications)
            or bool(proposal_actions) != bool(proposals)
            or (proposals and len(proposal_actions) != 1)
        ):
            raise ValueError("claim effects are invalid.")
        feedback_actions = tuple(
            action
            for action in actions
            if action.action_name == "record_blueprint_feedback"
        )
        feedback_decision = request.artifact_feedback_decision
        if (
            len(feedback) > 1
            or bool(feedback_actions) != bool(feedback)
            or (feedback and len(feedback_actions) != 1)
            or (feedback and feedback_decision is None)
            or any(
                item.feedback_id != f"feedback--{claim.ids.turn_id}"
                or item.artifact_id != feedback_decision.artifact_id
                or item.target_id != feedback_decision.target_id
                or item.decision != feedback_decision.decision
                or item.schema_version
                != feedback_decision.expected_schema_version
                for item in feedback
                if feedback_decision is not None
            )
        ):
            raise ValueError("claim effects are invalid.")
        synthesis_actions = tuple(
            action
            for action in actions
            if action.action_name == "synthesize_project"
        )
        artifact_actions = tuple(
            action
            for action in actions
            if action.action_name == "create_artifact"
        )
        artifact_effect_actions = synthesis_actions + artifact_actions
        if (
            len(artifacts) > 1
            or bool(artifact_effect_actions) != bool(artifacts)
            or (artifacts and len(artifact_effect_actions) != 1)
            or any(
                not self._artifact_matches_chat_turn_effect(
                    artifact,
                    request.project_id,
                    claim.ids.turn_id,
                    artifact_effect_actions[0].action_name
                    if artifact_effect_actions
                    else None,
                )
                for artifact in artifacts
            )
        ):
            raise ValueError("claim effects are invalid.")

    def _assert_chat_turn_claim_matches_document(
        self,
        claim: ChatTurnClaim,
        turn_data: Mapping[str, object],
    ) -> None:
        expected_decision = (
            claim.request.memory_decision.model_dump(mode="json")
            if claim.request.memory_decision is not None
            else None
        )
        expected_feedback_decision = (
            claim.request.artifact_feedback_decision.model_dump(mode="json")
            if claim.request.artifact_feedback_decision is not None
            else None
        )
        if (
            turn_data.get("schema_version") != CHAT_TURN_SCHEMA_VERSION
            or turn_data.get("project_id") != claim.request.project_id
            or turn_data.get("user_id") != claim.request.user_id
            or turn_data.get("memory_decision") != expected_decision
            or turn_data.get("artifact_feedback_decision")
            != expected_feedback_decision
            or turn_data.get("user_message_id")
            != claim.ids.user_message_id
            or turn_data.get("model_message_id")
            != claim.ids.model_message_id
            or not self._is_aware_datetime(turn_data.get("created_at"))
            or not self._is_aware_datetime(turn_data.get("updated_at"))
        ):
            raise ChatTurnStateError(
                "Stored chat turn does not match its claim."
            )

    def _chat_turn_replay(
        self,
        turn_data: Mapping[str, object],
        model_message_data: object,
    ) -> ChatTurnReplay:
        if not isinstance(model_message_data, Mapping):
            raise ChatTurnStateError("Stored model message is invalid.")
        if (
            set(model_message_data) != {"role", "text", "timestamp"}
            or model_message_data.get("role") != "model"
            or not self._is_aware_datetime(model_message_data.get("timestamp"))
            or not isinstance(model_message_data.get("text"), str)
        ):
            raise ChatTurnStateError("Stored model message is invalid.")
        if not self._is_aware_datetime(turn_data.get("completed_at")):
            raise ChatTurnStateError("Completed chat turn is invalid.")
        actions, memory_proposals, artifacts = self._chat_turn_effects(
            turn_data
        )
        memory_clarifications = self._chat_turn_memory_clarifications(
            turn_data
        )
        artifact_feedback = self._chat_turn_feedback_effects(
            turn_data,
            actions,
        )
        try:
            response = ChatResponse(
                response=model_message_data["text"],
                actions=list(actions),
                artifacts=list(artifacts),
                artifact_feedback=list(artifact_feedback),
                citations=turn_data.get("citations", []),
                memory_proposals=list(memory_proposals),
                memory_clarifications=list(memory_clarifications),
                adaptations=turn_data.get("adaptations", []),
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn response is invalid."
            ) from exc
        return ChatTurnReplay(response=response)

    @staticmethod
    def _chat_turn_effects(
        turn_data: Mapping[str, object],
    ) -> tuple[
        tuple[AgentActionReceipt, ...],
        tuple[VersionedMemoryProposalReceipt, ...],
        tuple[ArtifactReference, ...],
    ]:
        stored_actions = turn_data.get("actions", [])
        stored_proposals = turn_data.get("memory_proposals", [])
        stored_artifacts = turn_data.get("artifacts", [])
        if not isinstance(stored_actions, list) or not isinstance(
            stored_proposals,
            list,
        ) or not isinstance(stored_artifacts, list):
            raise ChatTurnStateError("Stored chat turn effects are invalid.")
        try:
            actions = tuple(
                AgentActionReceipt.model_validate(item)
                for item in stored_actions
            )
            proposals = tuple(
                MemoryEngine._proposal_receipt_from_document(item)
                for item in stored_proposals
            )
            artifacts = tuple(
                ArtifactReference.model_validate(item)
                for item in stored_artifacts
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn effects are invalid."
            ) from exc
        proposal_actions = tuple(
            action
            for action in actions
            if action.action_name == "propose_memory_signal"
        )
        if len(proposals) > 1 or bool(proposal_actions) != bool(proposals):
            raise ChatTurnStateError("Stored chat turn effects are invalid.")
        if proposals and len(proposal_actions) != 1:
            raise ChatTurnStateError("Stored chat turn effects are invalid.")
        synthesis_actions = tuple(
            action
            for action in actions
            if action.action_name == "synthesize_project"
        )
        artifact_actions = tuple(
            action
            for action in actions
            if action.action_name == "create_artifact"
        )
        artifact_effect_actions = synthesis_actions + artifact_actions
        model_message_id = turn_data.get("model_message_id")
        turn_id = (
            model_message_id.removeprefix("turn--").removesuffix("--model")
            if isinstance(model_message_id, str)
            else None
        )
        project_id = turn_data.get("project_id")
        if (
            len(artifacts) > 1
            or bool(artifact_effect_actions) != bool(artifacts)
            or (artifacts and len(artifact_effect_actions) != 1)
            or any(
                not MemoryEngine._artifact_matches_chat_turn_effect(
                    artifact,
                    project_id,
                    turn_id,
                    artifact_effect_actions[0].action_name
                    if artifact_effect_actions
                    else None,
                )
                for artifact in artifacts
            )
        ):
            raise ChatTurnStateError("Stored chat turn effects are invalid.")
        return actions, proposals, artifacts

    @staticmethod
    def _chat_turn_memory_clarifications(
        turn_data: Mapping[str, object],
    ) -> tuple[MemoryClarificationReceipt, ...]:
        stored_clarifications = turn_data.get(
            "memory_clarifications",
            [],
        )
        if not isinstance(stored_clarifications, list):
            raise ChatTurnStateError(
                "Stored chat turn clarification effects are invalid."
            )
        try:
            clarifications = tuple(
                MemoryClarificationReceipt.model_validate(item)
                for item in stored_clarifications
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn clarification effects are invalid."
            ) from exc
        if len(clarifications) > 1:
            raise ChatTurnStateError(
                "Stored chat turn clarification effects are invalid."
            )
        stored_proposals = turn_data.get("memory_proposals", [])
        if clarifications and stored_proposals:
            raise ChatTurnStateError(
                "Stored chat turn contains conflicting memory effects."
            )
        return clarifications

    @staticmethod
    def _artifact_matches_chat_turn_effect(
        artifact: ArtifactReference,
        project_id: object,
        turn_id: object,
        action_name: object,
    ) -> bool:
        if (
            not isinstance(project_id, str)
            or not isinstance(turn_id, str)
            or artifact.project_id != project_id
        ):
            return False
        if action_name == "synthesize_project":
            return (
                artifact.artifact_type == "synthesis_blueprint"
                and artifact.artifact_id == f"blueprint--{turn_id}"
                and artifact.schema_version == "2.0"
            )
        if action_name == "create_artifact":
            return (
                artifact.artifact_type == "single_file_artifact"
                and artifact.artifact_id == f"artifact--{turn_id}"
                and artifact.schema_version == "1.0"
            )
        return False

    @staticmethod
    def _chat_turn_feedback_effects(
        turn_data: Mapping[str, object],
        actions: tuple[AgentActionReceipt, ...],
    ) -> tuple[ArtifactFeedbackReference, ...]:
        stored_feedback = turn_data.get("artifact_feedback", [])
        if not isinstance(stored_feedback, list):
            raise ChatTurnStateError(
                "Stored chat turn feedback effects are invalid."
            )
        try:
            feedback = tuple(
                ArtifactFeedbackReference.model_validate(item)
                for item in stored_feedback
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn feedback effects are invalid."
            ) from exc
        feedback_actions = tuple(
            action
            for action in actions
            if action.action_name == "record_blueprint_feedback"
        )
        if (
            len(feedback) > 1
            or bool(feedback_actions) != bool(feedback)
            or (feedback and len(feedback_actions) != 1)
        ):
            raise ChatTurnStateError(
                "Stored chat turn feedback effects are invalid."
            )
        if not feedback:
            return ()
        try:
            decision = ArtifactFeedbackDecisionRequest.model_validate(
                turn_data.get("artifact_feedback_decision")
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn feedback effects are invalid."
            ) from exc
        model_message_id = turn_data.get("model_message_id")
        turn_id = (
            model_message_id.removeprefix("turn--").removesuffix("--model")
            if isinstance(model_message_id, str)
            else None
        )
        receipt = feedback[0]
        if (
            receipt.feedback_id != f"feedback--{turn_id}"
            or receipt.artifact_id != decision.artifact_id
            or receipt.target_id != decision.target_id
            or receipt.decision != decision.decision
            or receipt.schema_version != decision.expected_schema_version
        ):
            raise ChatTurnStateError(
                "Stored chat turn feedback effects are invalid."
            )
        return feedback

    @classmethod
    def _assert_chat_turn_response_preserves_effects(
        cls,
        turn_data: Mapping[str, object],
        response: ChatResponse,
    ) -> None:
        (
            stored_actions,
            stored_proposals,
            stored_artifacts,
        ) = cls._chat_turn_effects(turn_data)
        stored_feedback = cls._chat_turn_feedback_effects(
            turn_data,
            stored_actions,
        )
        stored_clarifications = cls._chat_turn_memory_clarifications(
            turn_data
        )
        response_actions = tuple(response.actions)
        response_proposals = tuple(response.memory_proposals)
        response_artifacts = tuple(response.artifacts)
        response_feedback = tuple(response.artifact_feedback)
        response_clarifications = tuple(response.memory_clarifications)
        stored_proposal_actions = tuple(
            action
            for action in stored_actions
            if action.action_name == "propose_memory_signal"
        )
        response_proposal_actions = tuple(
            action
            for action in response_actions
            if action.action_name == "propose_memory_signal"
        )
        if (
            stored_proposal_actions != response_proposal_actions
            or stored_proposals != response_proposals
            or stored_artifacts != response_artifacts
            or stored_feedback != response_feedback
            or stored_clarifications != response_clarifications
        ):
            raise ChatTurnStateError(
                "Completed response conflicts with stored turn effects."
            )
        for stored_action in stored_actions:
            if (
                stored_action.action_name != "propose_memory_signal"
                and stored_action not in response_actions
            ):
                raise ChatTurnStateError(
                    "Completed response omits a stored turn effect."
                )

    @staticmethod
    def _is_aware_datetime(value: object) -> bool:
        return (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() is not None
        )

    async def save_blueprint(
        self,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        schema_version: str,
        blueprint: dict[str, object],
        *,
        adaptations: tuple[AdaptationReceipt, ...] = (),
    ) -> str:
        """Atomically persist a project update and generated blueprint."""
        self._validate_string(project_id, "project_id")
        self._validate_string(session_id, "session_id")
        self._validate_string(user_id, "user_id")
        self._validate_string(model_name, "model_name")
        self._validate_string(schema_version, "schema_version")
        self._validate_blueprint(blueprint)
        adaptation_documents = self._adaptation_receipt_documents(
            adaptations
        )

        try:
            project_ref = self._client.collection("projects").document(
                project_id
            )
            blueprint_ref = project_ref.collection("blueprints").document()
            batch = self._client.batch()
            batch.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.set(
                blueprint_ref,
                {
                    "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
                    "artifact_type": "synthesis_blueprint",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "originating_session_id": session_id,
                    "originating_turn_id": None,
                    "user_id": user_id,
                    "model_name": model_name,
                    "schema_version": schema_version,
                    "parent_artifact_id": None,
                    "feedback_counts": {
                        "accepted": 0,
                        "rejected": 0,
                        "edited": 0,
                    },
                    "adaptation_receipts": adaptation_documents,
                    "applied_feedback_ids": [],
                    "blueprint": blueprint,
                },
            )
            await batch.commit()
            return blueprint_ref.id
        except GoogleAPIError as exc:
            self._raise_firestore_error("save_blueprint", exc)

    async def save_single_file_artifact(
        self,
        *,
        project_id: str,
        session_id: str,
        user_id: str,
        model_name: str,
        artifact: dict[str, object],
        display_label: str,
        originating_turn_id: str | None = None,
        parent_artifact_id: str | None = None,
    ) -> str:
        """Atomically persist one generic project-owned single-file artifact."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_string(session_id, "session_id")
        self._validate_string(user_id, "user_id")
        self._validate_string(model_name, "model_name")
        validated_artifact = SingleFileArtifact.model_validate(artifact)
        self._validate_string(display_label, "display_label")
        if originating_turn_id is not None:
            self._validate_memory_identifier(
                originating_turn_id,
                "originating_turn_id",
            )
        if parent_artifact_id is not None:
            self._validate_memory_identifier(
                parent_artifact_id,
                "parent_artifact_id",
            )

        try:
            project_ref = self._client.collection("projects").document(
                project_id
            )
            artifact_ref = project_ref.collection("artifacts").document()
            batch = self._client.batch()
            batch.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.set(
                artifact_ref,
                {
                    "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
                    "artifact_type": "single_file_artifact",
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "originating_session_id": session_id,
                    "originating_turn_id": originating_turn_id,
                    "user_id": user_id,
                    "model_name": model_name,
                    "schema_version": "1.0",
                    "display_label": display_label,
                    "parent_artifact_id": parent_artifact_id,
                    "lifecycle_status": "active",
                    "filename": validated_artifact.filename,
                    "artifact_family": validated_artifact.artifact_family,
                    "format": validated_artifact.format,
                    "byte_size": len(
                        validated_artifact.content.encode("utf-8")
                    ),
                    "content": validated_artifact.content,
                    "summary": validated_artifact.summary,
                },
            )
            await batch.commit()
            return artifact_ref.id
        except GoogleAPIError as exc:
            self._raise_firestore_error("save_single_file_artifact", exc)

    async def archive_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord:
        """Mark one project-owned generic artifact as archived."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(artifact_id, "artifact_id")

        try:
            artifact_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("artifacts")
                .document(artifact_id)
            )
            await artifact_ref.update(
                {
                    "lifecycle_status": "archived",
                    "archived_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )
            snapshot = await artifact_ref.get()
            if not snapshot.exists:
                raise ArtifactNotFoundError("Artifact does not exist.")
            document = snapshot.to_dict()
            if not isinstance(document, dict):
                raise ValueError("Stored artifact document is invalid.")
            return ArtifactDocumentRecord(
                artifact_id=artifact_id,
                document=document,
            )
        except ArtifactNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("archive_artifact_document", exc)
        except ValueError as exc:
            self._raise_firestore_error("archive_artifact_document", exc)

    async def restore_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord:
        """Mark one project-owned generic artifact as active."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(artifact_id, "artifact_id")

        try:
            artifact_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("artifacts")
                .document(artifact_id)
            )
            await artifact_ref.update(
                {
                    "lifecycle_status": "active",
                    "restored_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }
            )
            snapshot = await artifact_ref.get()
            if not snapshot.exists:
                raise ArtifactNotFoundError("Artifact does not exist.")
            document = snapshot.to_dict()
            if not isinstance(document, dict):
                raise ValueError("Stored artifact document is invalid.")
            return ArtifactDocumentRecord(
                artifact_id=artifact_id,
                document=document,
            )
        except ArtifactNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("restore_artifact_document", exc)
        except ValueError as exc:
            self._raise_firestore_error("restore_artifact_document", exc)

    async def update_artifact_metadata_document(
        self,
        project_id: str,
        artifact_id: str,
        *,
        display_label: str | None,
        filename: str | None,
    ) -> ArtifactDocumentRecord:
        """Update mutable public metadata for one project-owned artifact."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(artifact_id, "artifact_id")
        updates: dict[str, object] = {}
        if display_label is not None:
            self._validate_string(display_label, "display_label")
            updates["display_label"] = display_label
        if filename is not None:
            validated = SingleFileArtifact.model_validate(
                {
                    "artifact_family": "document",
                    "format": "text",
                    "filename": filename,
                    "content": "placeholder",
                }
            )
            updates["filename"] = validated.filename
        if not updates:
            raise ValueError("At least one metadata field is required.")
        updates["updated_at"] = firestore.SERVER_TIMESTAMP

        try:
            artifact_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("artifacts")
                .document(artifact_id)
            )
            await artifact_ref.update(updates)
            snapshot = await artifact_ref.get()
            if not snapshot.exists:
                raise ArtifactNotFoundError("Artifact does not exist.")
            document = snapshot.to_dict()
            if not isinstance(document, dict):
                raise ValueError("Stored artifact document is invalid.")
            return ArtifactDocumentRecord(
                artifact_id=artifact_id,
                document=document,
            )
        except ArtifactNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "update_artifact_metadata_document",
                exc,
            )
        except ValueError as exc:
            self._raise_firestore_error(
                "update_artifact_metadata_document",
                exc,
            )

    async def record_blueprint_feedback(
        self,
        *,
        project_id: str,
        blueprint_id: str,
        feedback_id: str,
        target_id: str,
        target_kind: str,
        decision: str,
        feedback_text: str,
        correction_text: str | None,
        supersedes_feedback_id: str | None,
        expected_schema_version: str,
        session_id: str,
        user_id: str,
        source_message_id: str,
        turn_id: str,
        observed_at: datetime,
    ) -> ArtifactFeedbackReference:
        """Create one immutable feedback event and update bounded counts."""
        for value, field_name in (
            (project_id, "project_id"),
            (blueprint_id, "blueprint_id"),
            (feedback_id, "feedback_id"),
            (target_id, "target_id"),
            (session_id, "session_id"),
            (user_id, "user_id"),
            (source_message_id, "source_message_id"),
            (turn_id, "turn_id"),
        ):
            self._validate_memory_identifier(value, field_name)
        if feedback_id != f"feedback--{turn_id}":
            raise ValueError("feedback_id must match its originating turn.")
        if supersedes_feedback_id is not None:
            self._validate_memory_identifier(
                supersedes_feedback_id,
                "supersedes_feedback_id",
            )
            if supersedes_feedback_id == feedback_id:
                raise ValueError("feedback cannot supersede itself.")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        request = ArtifactFeedbackDecisionRequest(
            artifact_id=blueprint_id,
            target_id=target_id,
            decision=decision,
            feedback_text=feedback_text,
            correction_text=correction_text,
            expected_schema_version=expected_schema_version,
            supersedes_feedback_id=supersedes_feedback_id,
        )
        reference = ArtifactFeedbackReference(
            feedback_id=feedback_id,
            artifact_id=blueprint_id,
            target_id=target_id,
            target_kind=target_kind,
            decision=request.decision,
            schema_version=request.expected_schema_version,
            created_at=observed_at,
        )
        project_ref = self._client.collection("projects").document(project_id)
        blueprint_ref = project_ref.collection("blueprints").document(
            blueprint_id
        )
        feedback_ref = blueprint_ref.collection("feedback").document(
            feedback_id
        )
        prior_feedback_ref = (
            blueprint_ref.collection("feedback").document(
                supersedes_feedback_id
            )
            if supersedes_feedback_id is not None
            else None
        )
        supersession_ref = (
            blueprint_ref.collection("feedback_supersessions").document(
                supersedes_feedback_id
            )
            if supersedes_feedback_id is not None
            else None
        )
        transaction = self._client.transaction()
        feedback_document = {
            "feedback_contract_version": "1.0",
            "feedback_id": feedback_id,
            "artifact_id": blueprint_id,
            "target_id": target_id,
            "target_kind": reference.target_kind,
            "decision": request.decision,
            "feedback_text": request.feedback_text,
            "correction_text": request.correction_text,
            "originating_session_id": session_id,
            "source_message_id": source_message_id,
            "originating_turn_id": turn_id,
            "user_id": user_id,
            "schema_version": request.expected_schema_version,
            "created_at": observed_at,
            "status": "active",
            "supersedes_feedback_id": supersedes_feedback_id,
        }
        supersession_document = (
            {
                "supersession_contract_version": "1.0",
                "supersedes_feedback_id": supersedes_feedback_id,
                "superseded_by_feedback_id": feedback_id,
                "created_at": observed_at,
            }
            if supersedes_feedback_id is not None
            else None
        )

        async def record_in_transaction(
            transaction: AsyncTransaction,
        ) -> ArtifactFeedbackReference:
            blueprint_snapshot = await blueprint_ref.get(
                transaction=transaction
            )
            if not blueprint_snapshot.exists:
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            blueprint_document = blueprint_snapshot.to_dict()
            if not isinstance(blueprint_document, Mapping):
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback state is invalid."
                )
            if blueprint_document.get("user_id") != user_id:
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            if (
                blueprint_document.get("artifact_contract_version")
                != ARTIFACT_CONTRACT_VERSION
                or blueprint_document.get("artifact_type")
                != "synthesis_blueprint"
            ):
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback state is invalid."
                )
            if (
                blueprint_document.get("schema_version")
                != request.expected_schema_version
            ):
                raise BlueprintFeedbackConflictError(
                    "Blueprint schema conflicts with feedback command."
                )
            try:
                counts = ArtifactFeedbackCounts.model_validate(
                    blueprint_document.get("feedback_counts", {})
                )
            except ValidationError as exc:
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback state is invalid."
                ) from exc

            prior_decision = None
            supersession_snapshot = None
            if prior_feedback_ref is not None:
                prior_snapshot = await prior_feedback_ref.get(
                    transaction=transaction
                )
                supersession_snapshot = await supersession_ref.get(
                    transaction=transaction
                )
                prior_document = prior_snapshot.to_dict()
                if (
                    not prior_snapshot.exists
                    or not isinstance(prior_document, Mapping)
                    or prior_document.get("feedback_contract_version")
                    != "1.0"
                    or prior_document.get("feedback_id")
                    != supersedes_feedback_id
                    or prior_document.get("artifact_id") != blueprint_id
                    or prior_document.get("target_id") != target_id
                    or prior_document.get("target_kind") != target_kind
                    or prior_document.get("user_id") != user_id
                    or prior_document.get("schema_version")
                    != request.expected_schema_version
                    or prior_document.get("status") != "active"
                    or not self._is_aware_datetime(
                        prior_document.get("created_at")
                    )
                    or prior_document.get("created_at") > observed_at
                ):
                    raise BlueprintFeedbackConflictError(
                        "Prior feedback cannot be superseded."
                    )
                prior_decision = prior_document.get("decision")
                if prior_decision not in {
                    "accepted",
                    "rejected",
                    "edited",
                }:
                    raise BlueprintFeedbackStateError(
                        "Stored prior feedback decision is invalid."
                    )
                if supersession_snapshot.exists:
                    existing_link = supersession_snapshot.to_dict()
                    existing_link_created_at = (
                        existing_link.get("created_at")
                        if isinstance(existing_link, Mapping)
                        else None
                    )
                    stable_existing_link = (
                        dict(existing_link)
                        if isinstance(existing_link, Mapping)
                        else {}
                    )
                    stable_existing_link.pop("created_at", None)
                    stable_supersession_document = dict(
                        supersession_document
                    )
                    stable_supersession_document.pop("created_at", None)
                    if (
                        not isinstance(existing_link, Mapping)
                        or not self._is_aware_datetime(
                            existing_link_created_at
                        )
                        or existing_link_created_at > observed_at
                        or stable_existing_link
                        != stable_supersession_document
                    ):
                        raise BlueprintFeedbackConflictError(
                            "Prior feedback is already superseded."
                        )

            existing_snapshot = await feedback_ref.get(
                transaction=transaction
            )
            if (
                supersession_snapshot is not None
                and existing_snapshot.exists
                != supersession_snapshot.exists
            ):
                raise BlueprintFeedbackStateError(
                    "Stored feedback supersession is incomplete."
                )
            if existing_snapshot.exists:
                existing_document = existing_snapshot.to_dict()
                if not isinstance(existing_document, Mapping):
                    raise BlueprintFeedbackStateError(
                        "Stored artifact feedback event is invalid."
                    )
                existing_created_at = existing_document.get("created_at")
                if (
                    not self._is_aware_datetime(existing_created_at)
                    or existing_created_at > observed_at
                ):
                    raise BlueprintFeedbackStateError(
                        "Stored artifact feedback event is invalid."
                    )
                stable_existing_document = dict(existing_document)
                stable_existing_document.pop("created_at", None)
                stable_feedback_document = dict(feedback_document)
                stable_feedback_document.pop("created_at", None)
                if stable_existing_document != stable_feedback_document:
                    raise BlueprintFeedbackConflictError(
                        "Feedback identifier conflicts with existing event."
                    )
                return reference.model_copy(
                    update={"created_at": existing_created_at}
                )

            count_values = counts.model_dump()
            if prior_decision is not None:
                if count_values[prior_decision] < 1:
                    raise BlueprintFeedbackStateError(
                        "Stored feedback counts cannot be superseded."
                    )
                count_values[prior_decision] -= 1
            count_values[request.decision] += 1
            updated_counts = ArtifactFeedbackCounts.model_validate(
                count_values
            )
            transaction.set(
                project_ref,
                {"updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            transaction.set(feedback_ref, feedback_document)
            if supersession_ref is not None:
                transaction.set(
                    supersession_ref,
                    supersession_document,
                )
            transaction.set(
                blueprint_ref,
                {"feedback_counts": updated_counts.model_dump()},
                merge=True,
            )
            return reference

        run_transaction = firestore.async_transactional(
            record_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (
            BlueprintArtifactNotFoundError,
            BlueprintFeedbackConflictError,
            BlueprintFeedbackStateError,
        ):
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("record_blueprint_feedback", exc)

    async def list_blueprint_documents(
        self,
        project_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> BlueprintDocumentPage:
        """Return one bounded newest-first page of project blueprints."""
        self._validate_memory_identifier(project_id, "project_id")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 50
        ):
            raise ValueError("limit must be an integer between 1 and 50.")
        if before is not None:
            self._validate_memory_identifier(before, "before")

        try:
            blueprints_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("blueprints")
            )
            query = blueprints_ref.order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            ).order_by(
                FieldPath.document_id(),
                direction=firestore.Query.DESCENDING,
            )
            if before is not None:
                cursor_snapshot = await blueprints_ref.document(before).get()
                if not cursor_snapshot.exists:
                    raise BlueprintArtifactCursorNotFoundError(
                        "Blueprint artifact cursor does not exist."
                    )
                query = query.start_after(cursor_snapshot)
            query = query.limit(limit + 1)

            records: list[BlueprintDocumentRecord] = []
            async for snapshot in query.stream():
                document = snapshot.to_dict()
                if not isinstance(document, dict):
                    raise ValueError("Stored blueprint document is invalid.")
                records.append(
                    BlueprintDocumentRecord(
                        artifact_id=snapshot.id,
                        document=document,
                    )
                )

            has_more = len(records) > limit
            bounded_records = tuple(records[:limit])
            next_before = (
                bounded_records[-1].artifact_id
                if has_more and bounded_records
                else None
            )
            return BlueprintDocumentPage(
                records=bounded_records,
                next_before=next_before,
            )
        except BlueprintArtifactCursorNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_blueprint_documents", exc)
        except ValueError as exc:
            self._raise_firestore_error("read_blueprint_documents", exc)

    async def get_artifact_document(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactDocumentRecord:
        """Return one project-owned generic artifact document."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(artifact_id, "artifact_id")

        try:
            artifact_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("artifacts")
                .document(artifact_id)
            )
            snapshot = await artifact_ref.get()
            if not snapshot.exists:
                raise ArtifactNotFoundError("Artifact does not exist.")
            document = snapshot.to_dict()
            if not isinstance(document, dict):
                raise ValueError("Stored artifact document is invalid.")
            return ArtifactDocumentRecord(
                artifact_id=artifact_id,
                document=document,
            )
        except ArtifactNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_artifact_document", exc)
        except ValueError as exc:
            self._raise_firestore_error("get_artifact_document", exc)

    async def list_artifact_documents(
        self,
        project_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> ArtifactDocumentPage:
        """Return one bounded newest-first page of project generic artifacts."""
        self._validate_memory_identifier(project_id, "project_id")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 50
        ):
            raise ValueError("limit must be an integer between 1 and 50.")
        if before is not None:
            self._validate_memory_identifier(before, "before")

        try:
            artifacts_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("artifacts")
            )
            query = artifacts_ref.order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            ).order_by(
                FieldPath.document_id(),
                direction=firestore.Query.DESCENDING,
            )
            if before is not None:
                cursor_snapshot = await artifacts_ref.document(before).get()
                if not cursor_snapshot.exists:
                    raise ArtifactCursorNotFoundError(
                        "Artifact cursor does not exist."
                    )
                query = query.start_after(cursor_snapshot)
            query = query.limit(limit + 1)

            records: list[ArtifactDocumentRecord] = []
            async for snapshot in query.stream():
                document = snapshot.to_dict()
                if not isinstance(document, dict):
                    raise ValueError("Stored artifact document is invalid.")
                records.append(
                    ArtifactDocumentRecord(
                        artifact_id=snapshot.id,
                        document=document,
                    )
                )

            has_more = len(records) > limit
            bounded_records = tuple(records[:limit])
            next_before = (
                bounded_records[-1].artifact_id
                if has_more and bounded_records
                else None
            )
            return ArtifactDocumentPage(
                records=bounded_records,
                next_before=next_before,
            )
        except ArtifactCursorNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("list_artifact_documents", exc)
        except ValueError as exc:
            self._raise_firestore_error("list_artifact_documents", exc)

    async def list_blueprint_feedback_documents(
        self,
        project_id: str,
        blueprint_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> BlueprintFeedbackDocumentPage:
        """Return one bounded page of immutable artifact feedback."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(blueprint_id, "blueprint_id")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 50
        ):
            raise ValueError("limit must be an integer between 1 and 50.")
        if before is not None:
            self._validate_memory_identifier(before, "before")

        try:
            blueprint_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("blueprints")
                .document(blueprint_id)
            )
            blueprint_snapshot = await blueprint_ref.get()
            if not blueprint_snapshot.exists:
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            blueprint_document = blueprint_snapshot.to_dict()
            if (
                not isinstance(blueprint_document, Mapping)
                or blueprint_document.get("artifact_contract_version")
                != ARTIFACT_CONTRACT_VERSION
                or blueprint_document.get("artifact_type")
                != "synthesis_blueprint"
                or blueprint_document.get("schema_version") != "2.0"
            ):
                raise BlueprintFeedbackStateError(
                    "Stored blueprint feedback parent is invalid."
                )
            feedback_ref = blueprint_ref.collection("feedback")
            supersessions_ref = blueprint_ref.collection(
                "feedback_supersessions"
            )
            query = feedback_ref.order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            ).order_by(
                FieldPath.document_id(),
                direction=firestore.Query.DESCENDING,
            )
            if before is not None:
                cursor_snapshot = await feedback_ref.document(before).get()
                if not cursor_snapshot.exists:
                    raise BlueprintFeedbackCursorNotFoundError(
                        "Artifact feedback cursor does not exist."
                    )
                query = query.start_after(cursor_snapshot)
            query = query.limit(limit + 1)

            snapshots = [snapshot async for snapshot in query.stream()]
            bounded_snapshots = snapshots[:limit]
            records: list[BlueprintFeedbackDocumentRecord] = []
            for snapshot in bounded_snapshots:
                document = snapshot.to_dict()
                if not isinstance(document, dict):
                    raise BlueprintFeedbackStateError(
                        "Stored artifact feedback event is invalid."
                    )
                link_snapshot = await supersessions_ref.document(
                    snapshot.id
                ).get()
                superseded_by_feedback_id = None
                if link_snapshot.exists:
                    link = link_snapshot.to_dict()
                    if (
                        not isinstance(link, Mapping)
                        or link.get("supersession_contract_version") != "1.0"
                        or link.get("supersedes_feedback_id") != snapshot.id
                        or not isinstance(
                            link.get("superseded_by_feedback_id"),
                            str,
                        )
                        or not self._is_aware_datetime(
                            link.get("created_at")
                        )
                    ):
                        raise BlueprintFeedbackStateError(
                            "Stored artifact feedback supersession is invalid."
                        )
                    superseded_by_feedback_id = link.get(
                        "superseded_by_feedback_id"
                    )
                records.append(
                    BlueprintFeedbackDocumentRecord(
                        feedback_id=snapshot.id,
                        document=document,
                        superseded_by_feedback_id=(
                            superseded_by_feedback_id
                        ),
                    )
                )

            has_more = len(snapshots) > limit
            next_before = (
                records[-1].feedback_id
                if has_more and records
                else None
            )
            return BlueprintFeedbackDocumentPage(
                records=tuple(records),
                next_before=next_before,
            )
        except (
            BlueprintArtifactNotFoundError,
            BlueprintFeedbackCursorNotFoundError,
            BlueprintFeedbackStateError,
        ):
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "list_blueprint_feedback_documents",
                exc,
            )

    async def get_blueprint_document(
        self,
        project_id: str,
        blueprint_id: str,
    ) -> BlueprintDocumentRecord:
        """Return one project-owned blueprint document by identifier."""
        self._validate_memory_identifier(project_id, "project_id")
        self._validate_memory_identifier(blueprint_id, "blueprint_id")

        try:
            blueprint_ref = (
                self._client.collection("projects")
                .document(project_id)
                .collection("blueprints")
                .document(blueprint_id)
            )
            snapshot = await blueprint_ref.get()
            if not snapshot.exists:
                raise BlueprintArtifactNotFoundError(
                    "Blueprint artifact does not exist."
                )
            document = snapshot.to_dict()
            if not isinstance(document, dict):
                raise ValueError("Stored blueprint document is invalid.")
            return BlueprintDocumentRecord(
                artifact_id=blueprint_id,
                document=document,
            )
        except BlueprintArtifactNotFoundError:
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_blueprint_document", exc)
        except ValueError as exc:
            self._raise_firestore_error("read_blueprint_document", exc)

    async def get_chat_history(
        self,
        session_id: str,
        limit: int | None = None,
        *,
        user_id: str,
        project_id: str,
        exclude_message_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return all or the newest session messages chronologically."""
        self._validate_string(session_id, "session_id")
        self._validate_string(user_id, "user_id")
        self._validate_string(project_id, "project_id")
        if limit is not None and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer between 1 and 100.")
        if exclude_message_id is not None:
            self._validate_string(
                exclude_message_id,
                "exclude_message_id",
            )
            if len(exclude_message_id) > 128:
                raise ValueError(
                    "exclude_message_id must not exceed 128 characters."
                )

        try:
            session_ref = self._client.collection("sessions").document(
                session_id
            )
            session_snapshot = await session_ref.get()
            if not session_snapshot.exists:
                return []
            self._validate_chat_session_owner(
                session_snapshot.to_dict(),
                user_id=user_id,
                project_id=project_id,
            )
            messages_ref = session_ref.collection("messages")
            direction = (
                firestore.Query.ASCENDING
                if limit is None
                else firestore.Query.DESCENDING
            )
            query = messages_ref.order_by(
                "timestamp",
                direction=direction,
            )
            if limit is not None:
                query = query.limit(
                    limit + 1 if exclude_message_id is not None else limit
                )

            history: list[dict[str, object]] = []

            async for snapshot in query.stream():
                if (
                    exclude_message_id is not None
                    and snapshot.id == exclude_message_id
                ):
                    continue
                data = snapshot.to_dict()
                if data is not None:
                    history.append(data)

            if limit is not None:
                history = history[:limit]
                history.reverse()

            return history
        except (ChatSessionOwnershipError, ChatTurnStateError):
            raise
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_chat_history", exc)

    async def update_user_profile(
        self, user_id: str, updates: dict[str, object]
    ) -> None:
        """Merge fields into a user's profile document."""
        self._validate_string(user_id, "user_id")
        self._validate_updates(updates)

        try:
            user_ref = self._client.collection("users").document(user_id)
            await user_ref.set(updates, merge=True)
        except GoogleAPIError as exc:
            self._raise_firestore_error("update_user_profile", exc)

    async def get_user_profile(self, user_id: str) -> dict[str, object]:
        """Return a user's profile or an empty dictionary when absent."""
        self._validate_string(user_id, "user_id")

        try:
            user_ref = self._client.collection("users").document(user_id)
            snapshot = await user_ref.get()

            if not snapshot.exists:
                return {}

            return snapshot.to_dict() or {}
        except GoogleAPIError as exc:
            self._raise_firestore_error("get_user_profile", exc)

    async def get_collaboration_profile(
        self,
        user_id: str,
    ) -> CollaborationProfile:
        """Load only the governed active-memory projection."""
        self._validate_memory_user_id(user_id)

        try:
            user_ref = self._client.collection("users").document(user_id)
            snapshot = await user_ref.get()
            if not snapshot.exists:
                return CollaborationProfile()
            return self._collaboration_profile_from_document(
                snapshot.to_dict()
            )
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("get_collaboration_profile", exc)

    async def get_memory_inspection(
        self,
        user_id: str,
        *,
        observed_at: datetime,
        after_event_id: str | None = None,
    ) -> MemoryInspectionPage:
        """Load bounded governed memory without exposing source messages."""
        self._validate_memory_user_id(user_id)
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError(
                "observed_at must be a timezone-aware datetime."
            )
        if after_event_id is not None:
            self._validate_memory_identifier(
                after_event_id,
                "after_event_id",
            )

        try:
            user_ref = self._client.collection("users").document(user_id)
            profile_snapshot = await user_ref.get()
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )

            proposal_collection = user_ref.collection("memory_proposals")
            proposal_refs = [
                proposal_collection.document(category)
                for category in MEMORY_CATEGORY_ORDER
            ]
            unresolved_by_category: dict[str, MemoryProposal] = {}
            async for snapshot in self._client.get_all(proposal_refs):
                if not snapshot.exists:
                    continue
                proposal = self._proposal_from_document(snapshot.to_dict())
                if (
                    proposal.status == "pending"
                    and observed_at < proposal.expires_at
                ):
                    unresolved_by_category[proposal.category] = proposal
            unresolved_proposals = tuple(
                unresolved_by_category[category]
                for category in MEMORY_CATEGORY_ORDER
                if category in unresolved_by_category
            )

            events_ref = user_ref.collection("memory_events")
            query = events_ref.order_by(
                "created_at",
                direction=firestore.Query.DESCENDING,
            )
            query = query.order_by(
                FieldPath.document_id(),
                direction=firestore.Query.DESCENDING,
            )
            if after_event_id is not None:
                cursor_ref = events_ref.document(after_event_id)
                cursor_snapshot = await cursor_ref.get()
                if not cursor_snapshot.exists:
                    raise MemoryEventCursorNotFoundError(
                        "Memory event cursor was not found."
                    )
                self._memory_event_from_document(
                    after_event_id,
                    cursor_snapshot.to_dict(),
                )
                query = query.start_after(cursor_snapshot)
            query = query.limit(51)
            event_snapshots = [snapshot async for snapshot in query.stream()]
            events = tuple(
                self._memory_event_from_document(
                    snapshot.id,
                    snapshot.to_dict(),
                )
                for snapshot in event_snapshots[:50]
            )
            next_event_id = (
                events[-1].event_id if len(event_snapshots) > 50 else None
            )

            return MemoryInspectionPage(
                profile=profile,
                unresolved_proposals=unresolved_proposals,
                events=events,
                next_event_id=next_event_id,
            )
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("get_memory_inspection", exc)

    async def create_memory_proposal(
        self,
        user_id: str,
        proposal: MemoryProposal,
        *,
        observed_at: datetime,
    ) -> MemoryProposal:
        """Create one pending proposal in its deterministic category slot."""
        self._validate_memory_proposal_creation(
            user_id,
            proposal,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            proposal.category
        )
        transaction = self._client.transaction()

        async def create_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryProposal:
            snapshot = await proposal_ref.get(transaction=transaction)
            if not snapshot.exists:
                transaction.set(
                    proposal_ref,
                    self._proposal_document(proposal),
                )
                return proposal
            stored = self._proposal_from_document(snapshot.to_dict())
            if stored.status == "pending" and stored.expires_at > observed_at:
                if self._proposals_are_identical(stored, proposal):
                    return stored
                raise MemoryProposalConflictError(
                    "An unexpired memory proposal already occupies this "
                    "category."
                )
            transaction.set(
                proposal_ref,
                self._proposal_document(proposal),
            )
            return proposal

        run_transaction = firestore.async_transactional(
            create_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("create_memory_proposal", exc)

    async def create_memory_clarification(
        self,
        *,
        envelope: MemoryClarificationEnvelope,
        observed_at: datetime,
        turn_lease: ProposalTurnLease | None,
    ) -> MemoryClarificationEnvelope:
        """Atomically persist one retry-safe clarification turn effect."""
        self._validate_memory_clarification_creation(
            envelope=envelope,
            observed_at=observed_at,
            turn_lease=turn_lease,
        )
        session_ref = self._client.collection("sessions").document(
            envelope.session_id
        )
        clarifications_ref = session_ref.collection(
            "memory_clarifications"
        )
        clarification_ref = clarifications_ref.document(
            envelope.clarification_id
        )
        turn_ref = session_ref.collection("turns").document(
            turn_lease.turn_id
        )
        transaction = self._client.transaction()

        async def create_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryClarificationEnvelope:
            session_snapshot = await session_ref.get(
                transaction=transaction
            )
            clarification_snapshot = await clarification_ref.get(
                transaction=transaction
            )
            turn_snapshot = await turn_ref.get(transaction=transaction)
            if not session_snapshot.exists:
                raise ChatTurnOwnershipError(
                    "Stored chat session cannot own a clarification effect."
                )
            session_document = session_snapshot.to_dict()
            self._validate_chat_session_owner(
                session_document,
                user_id=envelope.user_id,
                project_id=envelope.workspace_id,
            )
            active_id = session_document.get(
                "active_memory_clarification_id"
            )
            if active_id is not None:
                self._validate_memory_identifier(
                    active_id,
                    "active_memory_clarification_id",
                )

            if clarification_snapshot.exists:
                stored = self._memory_clarification_from_document(
                    clarification_snapshot.to_dict()
                )
                if stored != envelope:
                    raise MemoryClarificationConflictError(
                        "Stored clarification conflicts with this turn."
                    )
                if active_id != envelope.clarification_id:
                    raise MemoryClarificationStateError(
                        "Stored clarification is not the active session "
                        "clarification."
                    )
                effect = self._memory_clarification_turn_effect_update(
                    turn_snapshot=turn_snapshot,
                    envelope=envelope,
                    turn_lease=turn_lease,
                    observed_at=observed_at,
                )
                if effect is not None:
                    raise MemoryClarificationStateError(
                        "Stored clarification has no matching turn effect."
                    )
                return stored

            prior_ref = None
            prior = None
            if active_id is not None:
                prior_ref = clarifications_ref.document(active_id)
                prior_snapshot = await prior_ref.get(
                    transaction=transaction
                )
                if not prior_snapshot.exists:
                    raise MemoryClarificationStateError(
                        "Active clarification pointer has no document."
                    )
                prior = self._memory_clarification_from_document(
                    prior_snapshot.to_dict()
                )
                if (
                    prior.clarification_id != active_id
                    or prior.user_id != envelope.user_id
                    or prior.session_id != envelope.session_id
                    or prior.workspace_id != envelope.workspace_id
                    or prior.status != "open"
                ):
                    raise MemoryClarificationStateError(
                        "Active clarification pointer is invalid."
                    )

            effect = self._memory_clarification_turn_effect_update(
                turn_snapshot=turn_snapshot,
                envelope=envelope,
                turn_lease=turn_lease,
                observed_at=observed_at,
            )
            if prior_ref is not None and prior is not None:
                transaction.set(
                    prior_ref,
                    {"status": "expired"},
                    merge=True,
                )
            transaction.set(
                clarification_ref,
                envelope.model_dump(mode="python", exclude_none=True),
            )
            transaction.set(turn_ref, effect, merge=True)
            transaction.set(
                session_ref,
                {
                    "active_memory_clarification_id": (
                        envelope.clarification_id
                    ),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return envelope

        run_transaction = firestore.async_transactional(
            create_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "create_memory_clarification",
                exc,
            )

    async def create_guarded_memory_proposal(
        self,
        *,
        user_id: str,
        session_id: str,
        source_message_id: str,
        origin_ids: ProposalOriginIds,
        category: MemoryCategory,
        proposed_value: MemoryValue,
        observed_at: datetime,
        turn_lease: ProposalTurnLease | None,
    ) -> MemoryProposal:
        """Atomically create one source-message-guarded proposal."""
        self._validate_guarded_memory_proposal_inputs(
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message_id,
            origin_ids=origin_ids,
            category=category,
            proposed_value=proposed_value,
            observed_at=observed_at,
            turn_lease=turn_lease,
        )
        user_ref = self._client.collection("users").document(user_id)
        origin_ref = user_ref.collection(
            "memory_proposal_origins"
        ).document(origin_ids.origin_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        turn_ref = None
        if turn_lease is not None:
            turn_ref = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("turns")
                .document(turn_lease.turn_id)
            )
        transaction = self._client.transaction()

        async def create_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryProposal:
            origin_snapshot = await origin_ref.get(transaction=transaction)
            proposal_snapshot = await proposal_ref.get(
                transaction=transaction
            )
            profile_snapshot = await user_ref.get(transaction=transaction)
            turn_snapshot = (
                await turn_ref.get(transaction=transaction)
                if turn_ref is not None
                else None
            )
            if origin_snapshot.exists:
                origin_document = self._validated_proposal_origin_document(
                    origin_snapshot.to_dict()
                )
                expected_origin = {
                    "proposal_id": origin_ids.proposal_id,
                    "category": category,
                    "source_session_id": session_id,
                    "source_message_id": source_message_id,
                }
                if any(
                    origin_document[field_name] != expected_value
                    for field_name, expected_value in expected_origin.items()
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal origin conflicts with this source."
                    )
                if not proposal_snapshot.exists:
                    raise MemoryProposalStateError(
                        "Stored proposal origin has no category proposal."
                    )
                try:
                    stored_proposal = self._proposal_from_document(
                        proposal_snapshot.to_dict()
                    )
                except ValueError as exc:
                    raise MemoryProposalStateError(
                        "Stored guarded proposal is invalid."
                    ) from exc
                retry_profile = (
                    self._collaboration_profile_from_document(
                        profile_snapshot.to_dict()
                    )
                    if profile_snapshot.exists
                    else CollaborationProfile()
                )
                retry_active_signal = self._active_signal_for_category(
                    retry_profile,
                    category,
                )
                expected_proposal = {
                    "proposal_id": origin_ids.proposal_id,
                    "category": category,
                    "proposed_value": proposed_value,
                    "expected_signal_id": (
                        retry_active_signal.signal_id
                        if retry_active_signal is not None
                        else None
                    ),
                    "policy_version": "1.0",
                    "status": "pending",
                    "source_session_id": session_id,
                    "source_message_id": source_message_id,
                }
                if any(
                    getattr(stored_proposal, field_name) != expected_value
                    for field_name, expected_value in expected_proposal.items()
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal conflicts with this source."
                    )
                if turn_ref is not None:
                    turn_effect = self._proposal_turn_effect_update(
                        turn_snapshot=turn_snapshot,
                        user_id=user_id,
                        source_message_id=source_message_id,
                        turn_lease=turn_lease,
                        observed_at=observed_at,
                        proposal=stored_proposal,
                    )
                    if turn_effect is not None:
                        transaction.set(
                            turn_ref,
                            turn_effect,
                            merge=True,
                        )
                return stored_proposal
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            active_signal = self._active_signal_for_category(
                profile,
                category,
            )
            if (
                active_signal is not None
                and active_signal.value == proposed_value
            ):
                raise MemorySignalAlreadyActiveError(
                    "The proposed memory value is already active."
                )
            if proposal_snapshot.exists:
                stored_slot = self._proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                if (
                    stored_slot.status == "pending"
                    and stored_slot.expires_at > observed_at
                ):
                    raise MemoryProposalConflictError(
                        "An unexpired memory proposal already occupies this "
                        "category."
                    )
            proposal = MemoryProposal(
                proposal_id=origin_ids.proposal_id,
                category=category,
                proposed_value=proposed_value,
                expected_signal_id=(
                    active_signal.signal_id
                    if active_signal is not None
                    else None
                ),
                status="pending",
                source_session_id=session_id,
                source_message_id=source_message_id,
                created_at=observed_at,
                expires_at=observed_at + timedelta(hours=24),
            )
            turn_effect = None
            if turn_ref is not None:
                turn_effect = self._proposal_turn_effect_update(
                    turn_snapshot=turn_snapshot,
                    user_id=user_id,
                    source_message_id=source_message_id,
                    turn_lease=turn_lease,
                    observed_at=observed_at,
                    proposal=proposal,
                )
            transaction.set(
                proposal_ref,
                self._proposal_document(proposal),
            )
            transaction.set(
                origin_ref,
                {
                    "schema_version": PROPOSAL_ORIGIN_SCHEMA_VERSION,
                    "proposal_id": proposal.proposal_id,
                    "category": proposal.category,
                    "source_session_id": proposal.source_session_id,
                    "source_message_id": proposal.source_message_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                },
            )
            if turn_ref is not None and turn_effect is not None:
                transaction.set(
                    turn_ref,
                    turn_effect,
                    merge=True,
                )
            return proposal

        run_transaction = firestore.async_transactional(
            create_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error(
                "create_guarded_memory_proposal",
                exc,
            )

    async def create_guarded_memory_proposal_v2(
        self,
        *,
        user_id: str,
        session_id: str,
        source_message_id: str,
        evidence_message_id: str,
        clarification_id: str | None,
        origin_ids: ProposalOriginIds,
        category: MemoryCategoryV2,
        proposed_value: object,
        observed_at: datetime,
        turn_lease: ProposalTurnLease | None,
    ) -> MemoryProposalV2:
        """Atomically create one version-2 source-grounded proposal."""
        self._validate_memory_user_id(user_id)
        for field_name, value in (
            ("session_id", session_id),
            ("source_message_id", source_message_id),
            ("evidence_message_id", evidence_message_id),
        ):
            self._validate_memory_identifier(value, field_name)
        if clarification_id is not None:
            self._validate_memory_identifier(clarification_id, "clarification_id")
        if category not in MEMORY_CATEGORY_ORDER_V2:
            raise ValueError("category must be a governed memory category.")
        normalized_value = validate_memory_value_for_policy(
            "2.0", category, proposed_value
        )
        expected_ids = derive_proposal_origin_ids_v2(
            user_id, session_id, source_message_id, category
        )
        if origin_ids != expected_ids:
            raise ValueError("origin_ids must match the proposal source.")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if clarification_id is None:
            if evidence_message_id != source_message_id:
                raise ValueError(
                    "Direct memory evidence must match the source message."
                )
        elif evidence_message_id == source_message_id:
            raise ValueError(
                "Clarified memory evidence must precede the source message."
            )
        if turn_lease is not None and not isinstance(turn_lease, ProposalTurnLease):
            raise ValueError("turn_lease is invalid.")

        user_ref = self._client.collection("users").document(user_id)
        origin_ref = user_ref.collection("memory_proposal_origins").document(
            origin_ids.origin_id
        )
        proposal_ref = user_ref.collection("memory_proposals").document(category)
        turn_ref = None
        if turn_lease is not None:
            turn_ref = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("turns")
                .document(turn_lease.turn_id)
            )
        transaction = self._client.transaction()

        async def create_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryProposalV2:
            origin_snapshot = await origin_ref.get(transaction=transaction)
            proposal_snapshot = await proposal_ref.get(transaction=transaction)
            profile_snapshot = await user_ref.get(transaction=transaction)
            turn_snapshot = (
                await turn_ref.get(transaction=transaction)
                if turn_ref is not None
                else None
            )
            profile = (
                self._versioned_profile_from_document(profile_snapshot.to_dict())
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            active_signal = self._versioned_active_signal_for_category(
                profile, category
            )
            expected_signal_id = (
                active_signal.signal_id if active_signal is not None else None
            )
            if origin_snapshot.exists:
                try:
                    origin = parse_proposal_origin(origin_snapshot.to_dict())
                except ValueError as exc:
                    raise MemoryProposalStateError(
                        "Stored proposal origin is invalid."
                    ) from exc
                expected_origin = {
                    "schema_version": PROPOSAL_ORIGIN_SCHEMA_VERSION_V2,
                    "proposal_id": origin_ids.proposal_id,
                    "category": category,
                    "source_session_id": session_id,
                    "source_message_id": source_message_id,
                    "evidence_message_id": evidence_message_id,
                    "clarification_id": clarification_id,
                }
                if any(
                    getattr(origin, name) != value
                    for name, value in expected_origin.items()
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal origin conflicts with this source."
                    )
                if not proposal_snapshot.exists:
                    raise MemoryProposalStateError(
                        "Stored proposal origin has no category proposal."
                    )
                stored = self._versioned_proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                expected = {
                    "proposal_id": origin_ids.proposal_id,
                    "category": category,
                    "proposed_value": normalized_value,
                    "expected_signal_id": expected_signal_id,
                    "policy_version": "2.0",
                    "status": "pending",
                    "source_session_id": session_id,
                    "source_message_id": source_message_id,
                    "evidence_message_id": evidence_message_id,
                    "clarification_id": clarification_id,
                }
                if not isinstance(stored, MemoryProposalV2) or any(
                    getattr(stored, name) != value
                    for name, value in expected.items()
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal conflicts with this source."
                    )
                if turn_ref is not None:
                    effect = self._proposal_turn_effect_update(
                        turn_snapshot=turn_snapshot,
                        user_id=user_id,
                        source_message_id=source_message_id,
                        turn_lease=turn_lease,
                        observed_at=observed_at,
                        proposal=stored,
                    )
                    if effect is not None:
                        transaction.set(turn_ref, effect, merge=True)
                return stored

            if active_signal is not None and active_signal.value == normalized_value:
                raise MemorySignalAlreadyActiveError(
                    "The proposed memory value is already active."
                )
            if proposal_snapshot.exists:
                stored_slot = self._versioned_proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                if (
                    stored_slot.status == "pending"
                    and stored_slot.expires_at > observed_at
                ):
                    raise MemoryProposalConflictError(
                        "An unexpired memory proposal already occupies this category."
                    )
            proposal = MemoryProposalV2(
                proposal_id=origin_ids.proposal_id,
                category=category,
                proposed_value=normalized_value,
                expected_signal_id=expected_signal_id,
                status="pending",
                source_session_id=session_id,
                source_message_id=source_message_id,
                evidence_message_id=evidence_message_id,
                clarification_id=clarification_id,
                created_at=observed_at,
                expires_at=observed_at + timedelta(hours=24),
            )
            effect = None
            if turn_ref is not None:
                effect = self._proposal_turn_effect_update(
                    turn_snapshot=turn_snapshot,
                    user_id=user_id,
                    source_message_id=source_message_id,
                    turn_lease=turn_lease,
                    observed_at=observed_at,
                    proposal=proposal,
                )
            proposal_document = proposal.model_dump(mode="python")
            proposal_document["created_at"] = firestore.SERVER_TIMESTAMP
            transaction.set(proposal_ref, proposal_document)
            transaction.set(
                origin_ref,
                {
                    "schema_version": PROPOSAL_ORIGIN_SCHEMA_VERSION_V2,
                    "proposal_id": proposal.proposal_id,
                    "category": proposal.category,
                    "source_session_id": proposal.source_session_id,
                    "source_message_id": proposal.source_message_id,
                    "evidence_message_id": proposal.evidence_message_id,
                    "clarification_id": proposal.clarification_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                },
            )
            if turn_ref is not None and effect is not None:
                transaction.set(turn_ref, effect, merge=True)
            return proposal

        run_transaction = firestore.async_transactional(create_in_transaction)
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("create_guarded_memory_proposal_v2", exc)

    async def consume_memory_clarification_to_proposal_v2(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        source_message_id: str,
        selection: MemoryClarificationSelection,
        observed_at: datetime,
        turn_lease: ProposalTurnLease,
    ) -> MemoryProposalV2:
        """Consume the first subsequent clarification turn into one proposal."""
        self._validate_memory_user_id(user_id)
        for field_name, value in (
            ("workspace_id", workspace_id),
            ("session_id", session_id),
            ("source_message_id", source_message_id),
        ):
            self._validate_memory_identifier(value, field_name)
        if not isinstance(selection, MemoryClarificationSelection):
            raise ValueError("selection must be a memory clarification selection.")
        if not self._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if not isinstance(turn_lease, ProposalTurnLease):
            raise ValueError("turn_lease must be valid.")

        session_ref = self._client.collection("sessions").document(session_id)
        clarifications_ref = session_ref.collection("memory_clarifications")
        turn_ref = session_ref.collection("turns").document(turn_lease.turn_id)
        user_ref = self._client.collection("users").document(user_id)
        transaction = self._client.transaction()

        async def consume_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryProposalV2:
            session_snapshot = await session_ref.get(transaction=transaction)
            if not session_snapshot.exists:
                raise ChatTurnOwnershipError(
                    "Stored chat session cannot own a clarification selection."
                )
            session_document = session_snapshot.to_dict()
            self._validate_chat_session_owner(
                session_document,
                user_id=user_id,
                project_id=workspace_id,
            )
            if not isinstance(session_document, Mapping):
                raise MemoryClarificationStateError(
                    "Stored clarification session is invalid."
                )
            clarification_id = session_document.get(
                "active_memory_clarification_id"
            )
            if clarification_id is None:
                clarification_id = session_document.get(
                    "last_consumed_memory_clarification_id"
                )
                if (
                    clarification_id is None
                    or session_document.get("last_consuming_memory_turn_id")
                    != turn_lease.turn_id
                ):
                    raise MemoryClarificationStateError(
                        "No active memory clarification can be selected."
                    )
            self._validate_memory_identifier(
                clarification_id,
                "clarification_id",
            )
            clarification_ref = clarifications_ref.document(clarification_id)
            clarification_snapshot = await clarification_ref.get(
                transaction=transaction
            )
            if not clarification_snapshot.exists:
                raise MemoryClarificationStateError(
                    "Active clarification pointer has no document."
                )
            envelope = self._memory_clarification_from_document(
                clarification_snapshot.to_dict()
            )

            is_exact_retry = (
                envelope.status == "consumed"
                and envelope.consuming_turn_id == turn_lease.turn_id
                and envelope.consuming_message_id == source_message_id
                and envelope.selected_candidate_index
                == selection.selected_candidate_index
            )
            if is_exact_retry:
                candidate = envelope.candidates[
                    selection.selected_candidate_index
                ]
            else:
                try:
                    candidate = validate_memory_clarification_selection(
                        envelope=envelope,
                        selection=selection,
                        user_id=user_id,
                        session_id=session_id,
                        workspace_id=workspace_id,
                        selecting_turn_id=turn_lease.turn_id,
                        selecting_message_id=source_message_id,
                        is_first_subsequent_turn=(
                            session_document.get("last_completed_turn_id")
                            == envelope.clarification_turn_id
                        ),
                        observed_at=observed_at,
                    )
                except ValueError as exc:
                    raise MemoryClarificationStateError(str(exc)) from exc

            origin_ids = derive_proposal_origin_ids_v2(
                user_id,
                session_id,
                source_message_id,
                candidate.category,
            )
            origin_ref = user_ref.collection(
                "memory_proposal_origins"
            ).document(origin_ids.origin_id)
            proposal_ref = user_ref.collection("memory_proposals").document(
                candidate.category
            )
            origin_snapshot = await origin_ref.get(transaction=transaction)
            proposal_snapshot = await proposal_ref.get(transaction=transaction)
            profile_snapshot = await user_ref.get(transaction=transaction)
            turn_snapshot = await turn_ref.get(transaction=transaction)

            profile = (
                self._versioned_profile_from_document(profile_snapshot.to_dict())
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            active_signal = self._versioned_active_signal_for_category(
                profile,
                candidate.category,
            )
            expected_signal_id = (
                active_signal.signal_id if active_signal is not None else None
            )
            normalized_value = validate_memory_value_for_policy(
                "2.0",
                candidate.category,
                candidate.canonical_value,
            )

            if origin_snapshot.exists:
                try:
                    origin = parse_proposal_origin(origin_snapshot.to_dict())
                except ValueError as exc:
                    raise MemoryProposalStateError(
                        "Stored proposal origin is invalid."
                    ) from exc
                expected_origin = {
                    "schema_version": PROPOSAL_ORIGIN_SCHEMA_VERSION_V2,
                    "proposal_id": origin_ids.proposal_id,
                    "category": candidate.category,
                    "source_session_id": session_id,
                    "source_message_id": source_message_id,
                    "evidence_message_id": envelope.evidence_message_id,
                    "clarification_id": envelope.clarification_id,
                }
                if any(
                    getattr(origin, name) != value
                    for name, value in expected_origin.items()
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal origin conflicts with this selection."
                    )
                if not proposal_snapshot.exists:
                    raise MemoryProposalStateError(
                        "Stored proposal origin has no category proposal."
                    )
                stored = self._versioned_proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                if (
                    not isinstance(stored, MemoryProposalV2)
                    or stored.proposal_id != origin_ids.proposal_id
                    or stored.category != candidate.category
                    or stored.proposed_value != normalized_value
                    or stored.source_session_id != session_id
                    or stored.source_message_id != source_message_id
                    or stored.evidence_message_id != envelope.evidence_message_id
                    or stored.clarification_id != envelope.clarification_id
                ):
                    raise MemoryProposalOriginConflictError(
                        "Stored proposal conflicts with this selection."
                    )
                effect = self._proposal_turn_effect_update(
                    turn_snapshot=turn_snapshot,
                    user_id=user_id,
                    source_message_id=source_message_id,
                    turn_lease=turn_lease,
                    observed_at=observed_at,
                    proposal=stored,
                )
                if effect is not None:
                    transaction.set(turn_ref, effect, merge=True)
                return stored

            if active_signal is not None and active_signal.value == normalized_value:
                raise MemorySignalAlreadyActiveError(
                    "The selected memory value is already active."
                )
            if proposal_snapshot.exists:
                stored_slot = self._versioned_proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                if (
                    stored_slot.status == "pending"
                    and stored_slot.expires_at > observed_at
                ):
                    raise MemoryProposalConflictError(
                        "An unexpired memory proposal already occupies this category."
                    )
            proposal = MemoryProposalV2(
                proposal_id=origin_ids.proposal_id,
                category=candidate.category,
                proposed_value=normalized_value,
                expected_signal_id=expected_signal_id,
                status="pending",
                source_session_id=session_id,
                source_message_id=source_message_id,
                evidence_message_id=envelope.evidence_message_id,
                clarification_id=envelope.clarification_id,
                created_at=observed_at,
                expires_at=observed_at + timedelta(hours=24),
            )
            effect = self._proposal_turn_effect_update(
                turn_snapshot=turn_snapshot,
                user_id=user_id,
                source_message_id=source_message_id,
                turn_lease=turn_lease,
                observed_at=observed_at,
                proposal=proposal,
            )
            proposal_document = proposal.model_dump(mode="python")
            proposal_document["created_at"] = firestore.SERVER_TIMESTAMP
            transaction.set(proposal_ref, proposal_document)
            transaction.set(
                origin_ref,
                {
                    "schema_version": PROPOSAL_ORIGIN_SCHEMA_VERSION_V2,
                    "proposal_id": proposal.proposal_id,
                    "category": proposal.category,
                    "source_session_id": proposal.source_session_id,
                    "source_message_id": proposal.source_message_id,
                    "evidence_message_id": proposal.evidence_message_id,
                    "clarification_id": proposal.clarification_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                },
            )
            if effect is not None:
                transaction.set(turn_ref, effect, merge=True)
            transaction.set(
                clarification_ref,
                {
                    "status": "consumed",
                    "consuming_turn_id": turn_lease.turn_id,
                    "consuming_message_id": source_message_id,
                    "selected_candidate_index": (
                        selection.selected_candidate_index
                    ),
                },
                merge=True,
            )
            transaction.set(
                session_ref,
                {
                    "active_memory_clarification_id": firestore.DELETE_FIELD,
                    "last_consumed_memory_clarification_id": (
                        envelope.clarification_id
                    ),
                    "last_consuming_memory_turn_id": turn_lease.turn_id,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return proposal

        run_transaction = firestore.async_transactional(consume_in_transaction)
        try:
            return await run_transaction(transaction)
        except GoogleAPIError as exc:
            self._raise_firestore_error(
                "consume_memory_clarification_to_proposal_v2",
                exc,
            )

    async def approve_memory_proposal(
        self,
        user_id: str,
        category: MemoryCategory,
        proposal_id: str,
        *,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryApprovalResult:
        """Atomically approve one governed memory proposal."""
        self._validate_memory_approval_inputs(
            user_id,
            category,
            proposal_id,
            confirmation_channel,
            confirmation_session_id,
            confirmation_message_id,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        events_ref = user_ref.collection("memory_events")
        approved_event_id = f"{proposal_id}--approved"
        corrected_event_id = f"{proposal_id}--corrected"
        approved_event_ref = events_ref.document(approved_event_id)
        corrected_event_ref = events_ref.document(corrected_event_id)
        transaction = self._client.transaction()

        async def approve_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryApprovalResult:
            proposal_snapshot = await proposal_ref.get(transaction=transaction)
            profile_snapshot = await user_ref.get(transaction=transaction)
            approved_snapshot = await approved_event_ref.get(
                transaction=transaction
            )
            corrected_snapshot = await corrected_event_ref.get(
                transaction=transaction
            )

            if not proposal_snapshot.exists:
                raise MemoryProposalNotFoundError(
                    "Memory proposal does not exist."
                )
            proposal = self._proposal_from_document(
                proposal_snapshot.to_dict()
            )
            if (
                proposal.proposal_id != proposal_id
                or proposal.category != category
            ):
                raise MemoryProposalConflictError(
                    "Memory proposal no longer occupies this category."
                )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            if approved_snapshot.exists and corrected_snapshot.exists:
                raise ValueError(
                    "Stored memory approval has conflicting events."
                )
            if approved_snapshot.exists:
                return self._existing_initial_approval_result(
                    proposal,
                    profile,
                    approved_event_id,
                    approved_snapshot.to_dict(),
                    confirmation_channel,
                    confirmation_session_id,
                    confirmation_message_id,
                )
            if corrected_snapshot.exists:
                corrected_event = self._memory_event_from_document(
                    corrected_event_id,
                    corrected_snapshot.to_dict(),
                )
                prior_signal_id = corrected_event.related_signal_id
                if prior_signal_id is None:
                    raise MemoryProposalConflictError(
                        "Stored correction has no prior signal."
                    )
                superseded_event_id = f"{prior_signal_id}--superseded"
                if len(superseded_event_id) > 128:
                    raise ValueError("Derived memory event ID is too long.")
                superseded_event_ref = events_ref.document(
                    superseded_event_id
                )
                superseded_snapshot = await superseded_event_ref.get(
                    transaction=transaction
                )
                if not superseded_snapshot.exists:
                    raise ValueError(
                        "Stored correction has no superseded event."
                    )
                superseded_event = self._memory_event_from_document(
                    superseded_event_id,
                    superseded_snapshot.to_dict(),
                )
                return self._existing_correction_result(
                    proposal,
                    profile,
                    corrected_event,
                    superseded_event,
                    confirmation_channel,
                    confirmation_session_id,
                    confirmation_message_id,
                )
            if proposal.status == "approved":
                raise ValueError(
                    "Approved memory proposal has no lifecycle event."
                )
            if proposal.status != "pending":
                raise MemoryProposalConflictError(
                    "Memory proposal has already been resolved."
                )
            if proposal.expires_at <= observed_at:
                raise MemoryProposalExpiredError("Memory proposal has expired.")

            active_signal = self._active_signal_for_category(profile, category)
            if active_signal is not None:
                if proposal.expected_signal_id != active_signal.signal_id:
                    raise MemoryProposalConflictError(
                        "Memory proposal does not match the active signal."
                    )
                return await self._approve_correction_in_transaction(
                    transaction=transaction,
                    events_ref=events_ref,
                    corrected_event_ref=corrected_event_ref,
                    user_ref=user_ref,
                    proposal_ref=proposal_ref,
                    proposal=proposal,
                    profile=profile,
                    active_signal=active_signal,
                    corrected_event_id=corrected_event_id,
                    confirmation_channel=confirmation_channel,
                    confirmation_session_id=confirmation_session_id,
                    confirmation_message_id=confirmation_message_id,
                    observed_at=observed_at,
                )

            if proposal.expected_signal_id is not None:
                raise MemoryProposalConflictError(
                    "Memory proposal does not match the active signal."
                )

            revision = profile.memory_revision + 1
            event = self._proposal_memory_event(
                proposal,
                event_id=approved_event_id,
                event_type="approved",
                confirmation_channel=confirmation_channel,
                confirmation_session_id=confirmation_session_id,
                confirmation_message_id=confirmation_message_id,
                related_signal_id=None,
                memory_revision=revision,
                created_at=observed_at,
            )
            signal = self._active_signal_from_event(
                proposal,
                event,
                observed_at,
            )
            updated_profile = self._profile_with_signal(
                profile,
                signal,
                revision,
            )

            transaction.set(
                approved_event_ref,
                self._memory_event_document(event),
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(updated_profile),
                merge=True,
            )
            transaction.set(
                proposal_ref,
                {
                    "status": "approved",
                    "resolved_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return MemoryApprovalResult(
                profile=updated_profile,
                event=event,
            )

        run_transaction = firestore.async_transactional(
            approve_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("approve_memory_proposal", exc)

    async def reject_memory_proposal(
        self,
        user_id: str,
        category: MemoryCategory,
        proposal_id: str,
        *,
        observed_at: datetime,
    ) -> MemoryRejectionResult:
        """Atomically reject one pending governed-memory proposal."""
        self._validate_memory_signal_locator(
            user_id,
            category,
            proposal_id,
        )
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime.")

        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        transaction = self._client.transaction()

        async def reject_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryRejectionResult:
            proposal_snapshot = await proposal_ref.get(
                transaction=transaction
            )
            profile_snapshot = await user_ref.get(transaction=transaction)
            if not proposal_snapshot.exists:
                raise MemoryProposalNotFoundError(
                    "Memory proposal does not exist."
                )
            proposal = self._proposal_from_document(
                proposal_snapshot.to_dict()
            )
            if (
                proposal.proposal_id != proposal_id
                or proposal.category != category
            ):
                raise MemoryProposalConflictError(
                    "Memory proposal no longer occupies this category."
                )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            if proposal.status == "rejected":
                return MemoryRejectionResult(
                    profile=profile,
                    proposal=proposal,
                )
            if proposal.status != "pending":
                raise MemoryProposalConflictError(
                    "Memory proposal has already been resolved."
                )
            if proposal.expires_at <= observed_at:
                raise MemoryProposalExpiredError(
                    "Memory proposal has expired."
                )

            rejected_proposal = proposal.model_copy(
                update={"status": "rejected"}
            )
            transaction.set(
                proposal_ref,
                {
                    "status": "rejected",
                    "resolved_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return MemoryRejectionResult(
                profile=profile,
                proposal=rejected_proposal,
            )

        run_transaction = firestore.async_transactional(
            reject_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("reject_memory_proposal", exc)

    async def revoke_memory_signal(
        self,
        user_id: str,
        category: MemoryCategory,
        signal_id: str,
        *,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryRevocationResult:
        """Atomically remove an active signal and retain its history."""
        self._validate_memory_approval_inputs(
            user_id,
            category,
            signal_id,
            confirmation_channel,
            confirmation_session_id,
            confirmation_message_id,
            observed_at,
        )
        user_ref = self._client.collection("users").document(user_id)
        events_ref = user_ref.collection("memory_events")
        revoked_event_id = f"{signal_id}--revoked"
        revoked_event_ref = events_ref.document(revoked_event_id)
        transaction = self._client.transaction()

        async def revoke_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryRevocationResult:
            profile_snapshot = await user_ref.get(transaction=transaction)
            revoked_snapshot = await revoked_event_ref.get(
                transaction=transaction
            )
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            active_signal = self._active_signal_for_category(
                profile,
                category,
            )
            if active_signal is None or active_signal.signal_id != signal_id:
                if revoked_snapshot.exists:
                    revoked_event = self._memory_event_from_document(
                        revoked_event_id,
                        revoked_snapshot.to_dict(),
                    )
                    same_action = (
                        revoked_event.event_type == "revoked"
                        and revoked_event.signal_id == signal_id
                        and revoked_event.category == category
                        and revoked_event.confirmation_channel
                        == confirmation_channel
                        and revoked_event.confirmation_session_id
                        == confirmation_session_id
                        and revoked_event.confirmation_message_id
                        == confirmation_message_id
                        and revoked_event.related_signal_id is None
                    )
                    if not same_action:
                        raise MemorySignalConflictError(
                            "Stored memory revocation cannot prove this "
                            "action."
                        )
                    if profile.memory_revision < revoked_event.memory_revision:
                        raise ValueError(
                            "Stored memory revision precedes revoked event."
                        )
                    return MemoryRevocationResult(
                        profile=profile,
                        event=revoked_event,
                    )
                raise MemorySignalNotFoundError(
                    "Memory signal is not active."
                )
            if revoked_snapshot.exists:
                raise ValueError(
                    "Active memory signal already has a revoked event."
                )

            source_event_ref = events_ref.document(
                active_signal.source_event_id
            )
            source_snapshot = await source_event_ref.get(
                transaction=transaction
            )
            if not source_snapshot.exists:
                raise ValueError("Active memory source event does not exist.")
            source_event = self._memory_event_from_document(
                active_signal.source_event_id,
                source_snapshot.to_dict(),
            )
            self._validate_active_signal_source(active_signal, source_event)

            revision = profile.memory_revision + 1
            revoked_event = MemoryEvent.model_validate(
                {
                    "event_id": revoked_event_id,
                    "event_type": "revoked",
                    "signal_id": active_signal.signal_id,
                    "category": active_signal.category,
                    "value": active_signal.value,
                    "policy_version": active_signal.policy_version,
                    "source_type": source_event.source_type,
                    "source_session_id": source_event.source_session_id,
                    "source_message_id": source_event.source_message_id,
                    "confirmation_channel": confirmation_channel,
                    "confirmation_session_id": confirmation_session_id,
                    "confirmation_message_id": confirmation_message_id,
                    "related_signal_id": None,
                    "memory_revision": revision,
                    "created_at": observed_at,
                }
            )
            identity_context = dict(profile.identity_context)
            active_preferences = dict(profile.active_preferences)
            identity_context.pop(category, None)
            active_preferences.pop(category, None)
            updated_profile = CollaborationProfile(
                memory_schema_version="1.0",
                memory_revision=revision,
                identity_context=identity_context,
                active_preferences=active_preferences,
            )
            transaction.set(
                revoked_event_ref,
                self._memory_event_document(revoked_event),
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(
                    updated_profile,
                    refresh_approved_at=False,
                ),
                merge=True,
            )
            return MemoryRevocationResult(
                profile=updated_profile,
                event=revoked_event,
            )

        run_transaction = firestore.async_transactional(
            revoke_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("revoke_memory_signal", exc)

    async def delete_memory_signal(
        self,
        user_id: str,
        category: MemoryCategory,
        signal_id: str,
    ) -> MemoryDeletionResult:
        """Atomically remove every bounded artifact owned by a signal."""
        self._validate_memory_signal_locator(user_id, category, signal_id)
        user_ref = self._client.collection("users").document(user_id)
        proposal_ref = user_ref.collection("memory_proposals").document(
            category
        )
        origin_id = proposal_origin_id_from_signal_id(category, signal_id)
        origin_ref = (
            user_ref.collection("memory_proposal_origins").document(origin_id)
            if origin_id is not None
            else None
        )
        events_ref = user_ref.collection("memory_events")
        event_types = ("approved", "corrected", "superseded", "revoked")
        event_refs = {
            event_type: events_ref.document(f"{signal_id}--{event_type}")
            for event_type in event_types
        }
        transaction = self._client.transaction()

        async def delete_in_transaction(
            transaction: AsyncTransaction,
        ) -> MemoryDeletionResult:
            profile_snapshot = await user_ref.get(transaction=transaction)
            proposal_snapshot = await proposal_ref.get(
                transaction=transaction
            )
            origin_snapshot = (
                await origin_ref.get(transaction=transaction)
                if origin_ref is not None
                else None
            )
            event_snapshots = {
                event_type: await event_refs[event_type].get(
                    transaction=transaction
                )
                for event_type in event_types
            }
            profile = (
                self._collaboration_profile_from_document(
                    profile_snapshot.to_dict()
                )
                if profile_snapshot.exists
                else CollaborationProfile()
            )
            identity_context = dict(profile.identity_context)
            active_preferences = dict(profile.active_preferences)
            active_signal = self._active_signal_for_category(
                profile,
                category,
            )
            projection_owned = (
                active_signal is not None
                and active_signal.signal_id == signal_id
            )
            if projection_owned:
                identity_context.pop(category, None)
                active_preferences.pop(category, None)

            proposal_owned = False
            if proposal_snapshot.exists:
                proposal = self._proposal_from_document(
                    proposal_snapshot.to_dict()
                )
                proposal_owned = proposal.proposal_id == signal_id

            origin_owned = False
            if origin_snapshot is not None and origin_snapshot.exists:
                try:
                    origin_document = (
                        self._validated_proposal_origin_document(
                            origin_snapshot.to_dict()
                        )
                    )
                except MemoryProposalStateError as exc:
                    raise ValueError(
                        "Stored proposal origin does not match its path."
                    ) from exc
                if (
                    origin_document["proposal_id"] != signal_id
                    or origin_document["category"] != category
                ):
                    raise ValueError(
                        "Stored proposal origin does not match its path."
                    )
                origin_owned = True

            owned_event_types: list[str] = []
            for event_type, snapshot in event_snapshots.items():
                if not snapshot.exists:
                    continue
                event_id = f"{signal_id}--{event_type}"
                event = self._memory_event_from_document(
                    event_id,
                    snapshot.to_dict(),
                )
                if (
                    event.event_type != event_type
                    or event.signal_id != signal_id
                    or event.category != category
                ):
                    raise ValueError(
                        "Stored memory event does not match its path."
                    )
                owned_event_types.append(event_type)

            artifacts_deleted = bool(
                projection_owned
                or proposal_owned
                or origin_owned
                or owned_event_types
            )
            if not artifacts_deleted:
                return MemoryDeletionResult(
                    profile=profile,
                    artifacts_deleted=False,
                )

            updated_profile = CollaborationProfile(
                memory_schema_version="1.0",
                memory_revision=profile.memory_revision + 1,
                identity_context=identity_context,
                active_preferences=active_preferences,
            )
            transaction.set(
                user_ref,
                self._collaboration_profile_document(
                    updated_profile,
                    refresh_approved_at=False,
                ),
                merge=True,
            )
            if proposal_owned:
                transaction.delete(proposal_ref)
            if origin_owned:
                transaction.delete(origin_ref)
            for event_type in owned_event_types:
                transaction.delete(event_refs[event_type])
            return MemoryDeletionResult(
                profile=updated_profile,
                artifacts_deleted=True,
            )

        run_transaction = firestore.async_transactional(
            delete_in_transaction
        )
        try:
            return await run_transaction(transaction)
        except (GoogleAPIError, ValueError) as exc:
            self._raise_firestore_error("delete_memory_signal", exc)

    def close(self) -> None:
        """Close the Firestore client's transport."""
        self._client.close()

    @staticmethod
    def _chat_preview(text: str) -> str:
        compact = " ".join(text.split())
        return compact[:180]

    @staticmethod
    def _validate_limit(
        limit: object,
        field_name: str,
        *,
        maximum: int,
    ) -> None:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= maximum
        ):
            raise ValueError(
                f"{field_name} must be an integer between 1 and {maximum}."
            )

    @staticmethod
    def _proposal_document(proposal: MemoryProposal) -> dict[str, object]:
        document = proposal.model_dump(mode="python")
        document["created_at"] = firestore.SERVER_TIMESTAMP
        document["resolved_at"] = None
        return document

    @staticmethod
    def _active_signal_for_category(
        profile: CollaborationProfile,
        category: MemoryCategory,
    ) -> ActiveMemorySignal | None:
        if category in profile.identity_context:
            return profile.identity_context[category]
        if category in profile.active_preferences:
            return profile.active_preferences[category]
        return None

    @classmethod
    def _existing_initial_approval_result(
        cls,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        event_id: str,
        event_document: object,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
    ) -> MemoryApprovalResult:
        event = cls._memory_event_from_document(event_id, event_document)
        active_signal = cls._active_signal_for_category(
            profile,
            proposal.category,
        )
        expected_event = MemoryEvent.model_validate(
            {
                "event_id": event_id,
                "event_type": "approved",
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_type": "explicit_user_feedback",
                "source_session_id": proposal.source_session_id,
                "source_message_id": proposal.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": None,
                "memory_revision": profile.memory_revision,
                "created_at": event.created_at,
            }
        )
        valid_signal = (
            active_signal is not None
            and active_signal.signal_id == proposal.proposal_id
            and active_signal.category == proposal.category
            and active_signal.value == proposal.proposed_value
            and active_signal.policy_version == proposal.policy_version
            and active_signal.source_event_id == event_id
        )
        if (
            proposal.status != "approved"
            or event != expected_event
            or not valid_signal
        ):
            raise MemoryProposalConflictError(
                "Stored memory approval differs from this decision."
            )
        return MemoryApprovalResult(profile=profile, event=event)

    async def _approve_correction_in_transaction(
        self,
        *,
        transaction: AsyncTransaction,
        events_ref: AsyncCollectionReference,
        corrected_event_ref: AsyncDocumentReference,
        user_ref: AsyncDocumentReference,
        proposal_ref: AsyncDocumentReference,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        active_signal: ActiveMemorySignal,
        corrected_event_id: str,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        observed_at: datetime,
    ) -> MemoryApprovalResult:
        source_event_ref = events_ref.document(active_signal.source_event_id)
        superseded_event_id = f"{active_signal.signal_id}--superseded"
        if len(superseded_event_id) > 128:
            raise ValueError("Derived memory event ID is too long.")
        superseded_event_ref = events_ref.document(superseded_event_id)
        source_snapshot = await source_event_ref.get(transaction=transaction)
        superseded_snapshot = await superseded_event_ref.get(
            transaction=transaction
        )
        if not source_snapshot.exists:
            raise ValueError("Active memory source event does not exist.")
        source_event = self._memory_event_from_document(
            active_signal.source_event_id,
            source_snapshot.to_dict(),
        )
        self._validate_active_signal_source(active_signal, source_event)
        if superseded_snapshot.exists:
            raise MemoryProposalConflictError(
                "A differing superseded event already exists."
            )

        revision = profile.memory_revision + 1
        corrected_event = self._proposal_memory_event(
            proposal,
            event_id=corrected_event_id,
            event_type="corrected",
            confirmation_channel=confirmation_channel,
            confirmation_session_id=confirmation_session_id,
            confirmation_message_id=confirmation_message_id,
            related_signal_id=active_signal.signal_id,
            memory_revision=revision,
            created_at=observed_at,
        )
        superseded_event = MemoryEvent.model_validate(
            {
                "event_id": superseded_event_id,
                "event_type": "superseded",
                "signal_id": active_signal.signal_id,
                "category": active_signal.category,
                "value": active_signal.value,
                "policy_version": active_signal.policy_version,
                "source_type": source_event.source_type,
                "source_session_id": source_event.source_session_id,
                "source_message_id": source_event.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": proposal.proposal_id,
                "memory_revision": revision,
                "created_at": observed_at,
            }
        )
        signal = self._active_signal_from_event(
            proposal,
            corrected_event,
            observed_at,
        )
        updated_profile = self._profile_with_signal(
            profile,
            signal,
            revision,
        )
        transaction.set(
            corrected_event_ref,
            self._memory_event_document(corrected_event),
        )
        transaction.set(
            superseded_event_ref,
            self._memory_event_document(superseded_event),
        )
        transaction.set(
            user_ref,
            self._collaboration_profile_document(updated_profile),
            merge=True,
        )
        transaction.set(
            proposal_ref,
            {
                "status": "approved",
                "resolved_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return MemoryApprovalResult(
            profile=updated_profile,
            event=corrected_event,
            superseded_event=superseded_event,
        )

    @classmethod
    def _existing_correction_result(
        cls,
        proposal: MemoryProposal,
        profile: CollaborationProfile,
        corrected_event: MemoryEvent,
        superseded_event: MemoryEvent,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
    ) -> MemoryApprovalResult:
        prior_signal_id = corrected_event.related_signal_id
        active_signal = cls._active_signal_for_category(
            profile,
            proposal.category,
        )
        expected_corrected = cls._proposal_memory_event(
            proposal,
            event_id=corrected_event.event_id,
            event_type="corrected",
            confirmation_channel=confirmation_channel,
            confirmation_session_id=confirmation_session_id,
            confirmation_message_id=confirmation_message_id,
            related_signal_id=prior_signal_id,
            memory_revision=profile.memory_revision,
            created_at=corrected_event.created_at,
        )
        valid_active_signal = (
            active_signal is not None
            and active_signal.signal_id == proposal.proposal_id
            and active_signal.category == proposal.category
            and active_signal.value == proposal.proposed_value
            and active_signal.policy_version == proposal.policy_version
            and active_signal.source_event_id == corrected_event.event_id
        )
        valid_superseded = (
            prior_signal_id is not None
            and superseded_event.event_id
            == f"{prior_signal_id}--superseded"
            and superseded_event.event_type == "superseded"
            and superseded_event.signal_id == prior_signal_id
            and superseded_event.category == proposal.category
            and superseded_event.policy_version == proposal.policy_version
            and superseded_event.confirmation_channel == confirmation_channel
            and superseded_event.confirmation_session_id
            == confirmation_session_id
            and superseded_event.confirmation_message_id
            == confirmation_message_id
            and superseded_event.related_signal_id == proposal.proposal_id
            and superseded_event.memory_revision == profile.memory_revision
        )
        if (
            proposal.status != "approved"
            or proposal.expected_signal_id != prior_signal_id
            or corrected_event != expected_corrected
            or not valid_active_signal
            or not valid_superseded
        ):
            raise MemoryProposalConflictError(
                "Stored memory correction differs from this decision."
            )
        return MemoryApprovalResult(
            profile=profile,
            event=corrected_event,
            superseded_event=superseded_event,
        )

    @staticmethod
    def _proposal_memory_event(
        proposal: MemoryProposal,
        *,
        event_id: str,
        event_type: str,
        confirmation_channel: ConfirmationChannel,
        confirmation_session_id: str | None,
        confirmation_message_id: str | None,
        related_signal_id: str | None,
        memory_revision: int,
        created_at: datetime,
    ) -> MemoryEvent:
        return MemoryEvent.model_validate(
            {
                "event_id": event_id,
                "event_type": event_type,
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_type": "explicit_user_feedback",
                "source_session_id": proposal.source_session_id,
                "source_message_id": proposal.source_message_id,
                "confirmation_channel": confirmation_channel,
                "confirmation_session_id": confirmation_session_id,
                "confirmation_message_id": confirmation_message_id,
                "related_signal_id": related_signal_id,
                "memory_revision": memory_revision,
                "created_at": created_at,
            }
        )

    @staticmethod
    def _active_signal_from_event(
        proposal: MemoryProposal,
        event: MemoryEvent,
        approved_at: datetime,
    ) -> ActiveMemorySignal:
        return ActiveMemorySignal.model_validate(
            {
                "signal_id": proposal.proposal_id,
                "category": proposal.category,
                "value": proposal.proposed_value,
                "policy_version": proposal.policy_version,
                "source_event_id": event.event_id,
                "approved_at": approved_at,
            }
        )

    @staticmethod
    def _validate_active_signal_source(
        signal: ActiveMemorySignal,
        event: MemoryEvent,
    ) -> None:
        valid = (
            event.event_id == signal.source_event_id
            and event.signal_id == signal.signal_id
            and event.category == signal.category
            and event.value == signal.value
            and event.policy_version == signal.policy_version
            and event.event_type in ("approved", "corrected")
        )
        if not valid:
            raise ValueError(
                "Active memory signal does not match its source event."
            )

    @staticmethod
    def _profile_with_signal(
        profile: CollaborationProfile,
        signal: ActiveMemorySignal,
        revision: int,
    ) -> CollaborationProfile:
        identity_context = dict(profile.identity_context)
        active_preferences = dict(profile.active_preferences)
        if signal.category in ("preferred_name", "broad_roles"):
            identity_context[signal.category] = signal
        else:
            active_preferences[signal.category] = signal
        return CollaborationProfile(
            memory_schema_version="1.0",
            memory_revision=revision,
            identity_context=identity_context,
            active_preferences=active_preferences,
        )

    @staticmethod
    def _memory_event_document(event: MemoryEvent) -> dict[str, object]:
        document = event.model_dump(mode="python")
        document.pop("event_id")
        document["created_at"] = firestore.SERVER_TIMESTAMP
        return document

    @staticmethod
    def _memory_event_from_document(
        event_id: str,
        document: object,
    ) -> MemoryEvent:
        if not isinstance(document, dict):
            raise ValueError("Stored memory event is invalid.")
        event_fields = {
            field_name: document.get(field_name)
            for field_name in MemoryEvent.model_fields
            if field_name != "event_id"
        }
        event_fields["event_id"] = event_id
        return MemoryEvent.model_validate(event_fields)

    @staticmethod
    def _collaboration_profile_document(
        profile: CollaborationProfile,
        *,
        refresh_approved_at: bool = True,
    ) -> dict[str, object]:
        document = profile.model_dump(mode="python")
        if refresh_approved_at:
            for signals in (
                document["identity_context"],
                document["active_preferences"],
            ):
                for signal in signals.values():
                    signal["approved_at"] = firestore.SERVER_TIMESTAMP
        document["memory_updated_at"] = firestore.SERVER_TIMESTAMP
        return document

    @staticmethod
    def _validate_memory_proposal_creation(
        user_id: object,
        proposal: object,
        observed_at: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if not isinstance(proposal, MemoryProposal):
            raise ValueError("proposal must be a MemoryProposal.")
        if proposal.status != "pending":
            raise ValueError("proposal status must be pending.")

        proposal_prefix = f"{proposal.category}--"
        proposal_suffix = proposal.proposal_id.removeprefix(proposal_prefix)
        if (
            not proposal.proposal_id.startswith(proposal_prefix)
            or not proposal_suffix
        ):
            raise ValueError("proposal_id must match its category.")

        timestamps = (
            ("observed_at", observed_at),
            ("created_at", proposal.created_at),
            ("expires_at", proposal.expires_at),
        )
        for field_name, value in timestamps:
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError(
                    f"{field_name} must be a timezone-aware datetime."
                )

        if not proposal.created_at <= observed_at < proposal.expires_at:
            raise ValueError("proposal timestamps are not currently valid.")
        if proposal.expires_at - proposal.created_at != timedelta(hours=24):
            raise ValueError("proposal lifetime must be exactly 24 hours.")

    @staticmethod
    def _validate_guarded_memory_proposal_inputs(
        *,
        user_id: object,
        session_id: object,
        source_message_id: object,
        origin_ids: object,
        category: object,
        proposed_value: object,
        observed_at: object,
        turn_lease: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        MemoryEngine._validate_memory_identifier(session_id, "session_id")
        MemoryEngine._validate_memory_identifier(
            source_message_id,
            "source_message_id",
        )
        if category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        normalized_value = validate_memory_value(category, proposed_value)
        if normalized_value != proposed_value:
            raise ValueError("proposed_value must already be normalized.")
        if not isinstance(origin_ids, ProposalOriginIds):
            raise ValueError("origin_ids must be valid proposal IDs.")
        expected_ids = derive_proposal_origin_ids(
            user_id,
            session_id,
            source_message_id,
            category,
        )
        if origin_ids != expected_ids:
            raise ValueError("origin_ids do not match proposal provenance.")
        if not MemoryEngine._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if turn_lease is not None and not isinstance(
            turn_lease,
            ProposalTurnLease,
        ):
            raise ValueError("turn_lease must be valid when provided.")

    @staticmethod
    def _validate_memory_clarification_creation(
        *,
        envelope: object,
        observed_at: object,
        turn_lease: object,
    ) -> None:
        if not isinstance(envelope, MemoryClarificationEnvelope):
            raise ValueError("envelope must be a memory clarification.")
        if envelope.status != "open":
            raise ValueError("Only an open clarification can be created.")
        if not isinstance(turn_lease, ProposalTurnLease):
            raise ValueError("A valid turn lease is required.")
        if turn_lease.turn_id != envelope.clarification_turn_id:
            raise ValueError("The turn lease does not own the clarification.")
        if not MemoryEngine._is_aware_datetime(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime.")
        if not envelope.created_at <= observed_at < envelope.expires_at:
            raise ValueError("Clarification timestamps are not currently valid.")
        expected_id = derive_memory_clarification_id(
            user_id=envelope.user_id,
            session_id=envelope.session_id,
            evidence_message_id=envelope.evidence_message_id,
            clarification_turn_id=envelope.clarification_turn_id,
        )
        if envelope.clarification_id != expected_id:
            raise ValueError("clarification_id does not match provenance.")

    @staticmethod
    def _memory_clarification_from_document(
        document: object,
    ) -> MemoryClarificationEnvelope:
        if not isinstance(document, dict):
            raise MemoryClarificationStateError(
                "Stored clarification is invalid."
            )
        try:
            envelope = MemoryClarificationEnvelope.model_validate(document)
        except ValidationError as exc:
            raise MemoryClarificationStateError(
                "Stored clarification is invalid."
            ) from exc
        expected_id = derive_memory_clarification_id(
            user_id=envelope.user_id,
            session_id=envelope.session_id,
            evidence_message_id=envelope.evidence_message_id,
            clarification_turn_id=envelope.clarification_turn_id,
        )
        if envelope.clarification_id != expected_id:
            raise MemoryClarificationStateError(
                "Stored clarification is invalid."
            )
        return envelope

    @staticmethod
    def _memory_clarification_turn_effect_update(
        *,
        turn_snapshot: object,
        envelope: MemoryClarificationEnvelope,
        turn_lease: ProposalTurnLease,
        observed_at: datetime,
    ) -> dict[str, object] | None:
        if not getattr(turn_snapshot, "exists", False):
            raise ChatTurnOwnershipError(
                "Stored chat turn cannot own a clarification effect."
            )
        turn_data = turn_snapshot.to_dict()
        if not isinstance(turn_data, Mapping):
            raise ChatTurnStateError("Stored chat turn is invalid.")
        lease_expires_at = turn_data.get("lease_expires_at")
        if (
            turn_data.get("schema_version") != CHAT_TURN_SCHEMA_VERSION
            or turn_data.get("status") != "in_progress"
            or turn_data.get("project_id") != envelope.workspace_id
            or turn_data.get("user_id") != envelope.user_id
            or turn_data.get("user_message_id")
            != envelope.evidence_message_id
            or turn_data.get("lease_owner") != turn_lease.owner_token
            or not MemoryEngine._is_aware_datetime(lease_expires_at)
            or lease_expires_at <= observed_at
        ):
            raise ChatTurnOwnershipError(
                "Stored chat turn cannot own a clarification effect."
            )
        receipt = clarification_receipt(envelope).model_dump(mode="python")
        existing = turn_data.get("memory_clarifications", [])
        if not isinstance(existing, list):
            raise ChatTurnStateError(
                "Stored clarification turn effects are invalid."
            )
        try:
            validated = [
                MemoryClarificationReceipt.model_validate(item).model_dump(
                    mode="python"
                )
                for item in existing
            ]
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored clarification turn effects are invalid."
            ) from exc
        if validated:
            if validated == [receipt]:
                return None
            raise ChatTurnStateError(
                "Stored chat turn has conflicting clarification effects."
            )
        return {
            "memory_clarifications": [receipt],
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

    @staticmethod
    def _validated_proposal_origin_document(
        document: object,
    ) -> dict[str, object]:
        if not isinstance(document, dict):
            raise MemoryProposalStateError(
                "Stored proposal origin is invalid."
            )
        required_fields = {
            "schema_version",
            "proposal_id",
            "category",
            "source_session_id",
            "source_message_id",
            "created_at",
        }
        if set(document) != required_fields:
            raise MemoryProposalStateError(
                "Stored proposal origin is invalid."
            )
        if (
            document["schema_version"] != PROPOSAL_ORIGIN_SCHEMA_VERSION
            or document["category"] not in MEMORY_CATEGORY_ORDER
            or not MemoryEngine._is_aware_datetime(document["created_at"])
        ):
            raise MemoryProposalStateError(
                "Stored proposal origin is invalid."
            )
        for field_name in (
            "proposal_id",
            "source_session_id",
            "source_message_id",
        ):
            MemoryEngine._validate_memory_identifier(
                document[field_name],
                field_name,
            )
        return document

    @staticmethod
    def _proposal_turn_effect_update(
        *,
        turn_snapshot: object,
        user_id: str,
        source_message_id: str,
        turn_lease: ProposalTurnLease | None,
        observed_at: datetime,
        proposal: VersionedMemoryProposal,
    ) -> dict[str, object] | None:
        if turn_lease is None:
            raise ValueError("turn_lease is required for a turn effect.")
        if (
            turn_snapshot is None
            or not getattr(turn_snapshot, "exists", False)
        ):
            raise ChatTurnOwnershipError(
                "Stored chat turn cannot own a proposal effect."
            )
        turn_data = turn_snapshot.to_dict()
        if not isinstance(turn_data, Mapping):
            raise ChatTurnStateError("Stored chat turn is invalid.")
        lease_expires_at = turn_data.get("lease_expires_at")
        if (
            turn_data.get("schema_version") != CHAT_TURN_SCHEMA_VERSION
            or turn_data.get("status") != "in_progress"
            or turn_data.get("user_id") != user_id
            or turn_data.get("user_message_id") != source_message_id
            or turn_data.get("lease_owner") != turn_lease.owner_token
            or not MemoryEngine._is_aware_datetime(lease_expires_at)
            or lease_expires_at <= observed_at
        ):
            raise ChatTurnOwnershipError(
                "Stored chat turn cannot own a proposal effect."
            )
        action = AgentActionReceipt(
            action_name="propose_memory_signal",
            status="completed",
        ).model_dump(mode="python")
        receipt = MemoryEngine._proposal_receipt(proposal).model_dump(
            mode="python"
        )
        existing_actions = turn_data.get("actions", [])
        existing_proposals = turn_data.get("memory_proposals", [])
        if not isinstance(existing_actions, list) or not isinstance(
            existing_proposals,
            list,
        ):
            raise ChatTurnStateError("Stored chat turn effects are invalid.")
        try:
            validated_actions = [
                AgentActionReceipt.model_validate(item).model_dump(
                    mode="python"
                )
                for item in existing_actions
            ]
            validated_proposals = [
                MemoryEngine._proposal_receipt_from_document(item).model_dump(
                    mode="python"
                )
                for item in existing_proposals
            ]
        except (ValidationError, TypeError, ValueError) as exc:
            raise ChatTurnStateError(
                "Stored chat turn effects are invalid."
            ) from exc
        proposal_actions = [
            item
            for item in validated_actions
            if item["action_name"] == "propose_memory_signal"
        ]
        if proposal_actions or validated_proposals:
            if (
                proposal_actions == [action]
                and validated_proposals == [receipt]
            ):
                return None
            raise ChatTurnStateError(
                "Stored chat turn has conflicting proposal effects."
            )
        return {
            "actions": [*validated_actions, action],
            "memory_proposals": [receipt],
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

    @staticmethod
    def _proposal_receipt(
        proposal: VersionedMemoryProposal,
    ) -> VersionedMemoryProposalReceipt:
        fields = {
            "proposal_id": proposal.proposal_id,
            "category": proposal.category,
            "proposed_value": proposal.proposed_value,
            "expires_at": proposal.expires_at,
        }
        if isinstance(proposal, MemoryProposalV2):
            return MemoryProposalReceiptV2(
                **fields,
                policy_version="2.0",
            )
        return MemoryProposalReceipt(**fields)

    @staticmethod
    def _proposal_receipt_from_document(
        document: object,
    ) -> VersionedMemoryProposalReceipt:
        if not isinstance(document, Mapping):
            raise ValueError("Stored memory proposal receipt is invalid.")
        if document.get("policy_version") == "2.0":
            return MemoryProposalReceiptV2.model_validate(document)
        return MemoryProposalReceipt.model_validate(document)

    @staticmethod
    def _validate_memory_approval_inputs(
        user_id: object,
        category: object,
        proposal_id: object,
        confirmation_channel: object,
        confirmation_session_id: object,
        confirmation_message_id: object,
        observed_at: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        if not isinstance(proposal_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", proposal_id
        ) is None:
            raise ValueError("proposal_id must be a valid identifier.")
        if not proposal_id.startswith(f"{category}--"):
            raise ValueError("proposal_id must match its category.")
        for suffix in ("--approved", "--corrected", "--superseded"):
            if len(f"{proposal_id}{suffix}") > 128:
                raise ValueError("Derived memory event ID is too long.")
        if confirmation_channel == "chat_decision":
            MemoryEngine._validate_memory_identifier(
                confirmation_session_id,
                "confirmation_session_id",
            )
            MemoryEngine._validate_memory_identifier(
                confirmation_message_id,
                "confirmation_message_id",
            )
        elif confirmation_channel == "memory_api":
            if (
                confirmation_session_id is not None
                or confirmation_message_id is not None
            ):
                raise ValueError(
                    "Memory API confirmation IDs must be omitted."
                )
        else:
            raise ValueError("confirmation_channel is invalid.")
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime.")

    @staticmethod
    def _validate_memory_signal_locator(
        user_id: object,
        category: object,
        signal_id: object,
    ) -> None:
        MemoryEngine._validate_memory_user_id(user_id)
        if category not in MEMORY_CATEGORY_ORDER:
            raise ValueError("category must be a governed memory category.")
        if not isinstance(signal_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            signal_id,
        ) is None:
            raise ValueError("signal_id must be a valid identifier.")
        if not signal_id.startswith(f"{category}--"):
            raise ValueError("signal_id must match its category.")
        for suffix in (
            "--approved",
            "--corrected",
            "--superseded",
            "--revoked",
        ):
            if len(f"{signal_id}{suffix}") > 128:
                raise ValueError("Derived memory event ID is too long.")

    @staticmethod
    def _proposal_from_document(
        document: object,
    ) -> MemoryProposal:
        if not isinstance(document, dict):
            raise ValueError("Stored memory proposal is invalid.")
        proposal_fields = {
            field_name: document.get(field_name)
            for field_name in MemoryProposal.model_fields
        }
        return MemoryProposal.model_validate(proposal_fields)

    @staticmethod
    def _versioned_proposal_from_document(
        document: object,
    ) -> VersionedMemoryProposal:
        if not isinstance(document, Mapping):
            raise ValueError("Stored memory proposal is invalid.")
        if document.get("policy_version", "1.0") == "2.0":
            fields = {
                field_name: document.get(field_name)
                for field_name in MemoryProposalV2.model_fields
            }
            return MemoryProposalV2.model_validate(fields)
        return MemoryEngine._proposal_from_document(dict(document))

    @staticmethod
    def _collaboration_profile_from_document(
        document: object,
    ) -> CollaborationProfile:
        if not isinstance(document, dict):
            raise ValueError("Stored collaboration profile is invalid.")
        profile_fields = {
            field_name: document[field_name]
            for field_name in CollaborationProfile.model_fields
            if field_name in document
        }
        return CollaborationProfile.model_validate(profile_fields)

    @staticmethod
    def _versioned_profile_from_document(
        document: object,
    ) -> VersionedCollaborationProfile:
        if not isinstance(document, Mapping):
            raise ValueError("Stored collaboration profile is invalid.")
        governed_fields = {
            field_name: document[field_name]
            for field_name in CollaborationProfileV2.model_fields
            if field_name in document
        }
        return parse_collaboration_profile(governed_fields)

    @staticmethod
    def _versioned_active_signal_for_category(
        profile: VersionedCollaborationProfile,
        category: MemoryCategoryV2,
    ) -> object | None:
        if category in profile.identity_context:
            return profile.identity_context[category]
        if category in profile.active_preferences:
            return profile.active_preferences[category]
        return None

    @staticmethod
    def _proposals_are_identical(
        stored: MemoryProposal,
        candidate: MemoryProposal,
    ) -> bool:
        stable_fields = (
            "proposal_id",
            "category",
            "proposed_value",
            "expected_signal_id",
            "policy_version",
            "source_session_id",
            "source_message_id",
            "expires_at",
        )
        return all(
            getattr(stored, field_name) == getattr(candidate, field_name)
            for field_name in stable_fields
        )

    @staticmethod
    def _validate_memory_user_id(user_id: object) -> None:
        if not isinstance(user_id, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            user_id,
        ) is None:
            raise ValueError("user_id must be a valid identifier.")

    @staticmethod
    def _validate_memory_identifier(value: object, field_name: str) -> None:
        if not isinstance(value, str) or re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}",
            value,
        ) is None:
            raise ValueError(f"{field_name} must be a valid identifier.")

    @staticmethod
    def _validate_string(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string.")

    @staticmethod
    def _validate_updates(updates: object) -> None:
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dictionary.")

    @staticmethod
    def _validate_blueprint(blueprint: object) -> None:
        if not isinstance(blueprint, dict) or not blueprint:
            raise ValueError("blueprint must be a non-empty dictionary.")

    @staticmethod
    def _adaptation_receipt_documents(
        adaptations: object,
    ) -> list[dict[str, object]]:
        if (
            not isinstance(adaptations, tuple)
            or len(adaptations) > 8
            or not all(
                isinstance(receipt, AdaptationReceipt)
                for receipt in adaptations
            )
        ):
            raise ValueError("adaptations must be valid adaptation receipts.")
        categories = [receipt.category for receipt in adaptations]
        if len(categories) != len(set(categories)):
            raise ValueError("adaptation receipt categories must be unique.")
        return [
            receipt.model_dump(mode="python") for receipt in adaptations
        ]

    @staticmethod
    def _raise_firestore_error(
        operation: str, error: Exception
    ) -> NoReturn:
        logger.error("Firestore %s operation failed.", operation)
        raise MemoryEngineError(
            f"Firestore {operation} operation failed."
        ) from error
