from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from database import MemoryEngine
from collaborative_note_candidates import (
    NoteCandidateDecision,
    NaturalCollaborativeNoteDecision,
    validate_note_candidate_evidence,
)
from collaborative_note_policy import CollaborativeNoteKind
from schemas import (
    AgentActionReceipt,
    CollaborativeNote,
    CollaborativeNoteEvent,
    CollaborativeNoteProposal,
    MemoryDecision,
)

CollaborativeNoteStatusFilter = Literal["active", "archived"]


@dataclass(frozen=True, slots=True)
class ListCollaborativeNotesCommand:
    user_id: str
    workspace_id: str
    status_filter: CollaborativeNoteStatusFilter
    limit: int
    cursor: str | None


@dataclass(frozen=True, slots=True)
class GetCollaborativeNoteCommand:
    user_id: str
    workspace_id: str
    note_id: str
    limit: int


@dataclass(frozen=True, slots=True)
class CollaborativeNoteCorrectionCommand:
    user_id: str
    workspace_id: str
    note_id: str
    expected_revision: int
    note_kind: CollaborativeNoteKind
    title: str
    body: str
    source_session_id: str
    source_message_ids: tuple[str, ...]
    idempotency_key: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CollaborativeNoteProposalCommand:
    user_id: str
    workspace_id: str
    session_id: str
    note_kind: CollaborativeNoteKind
    title: str
    body: str
    idempotency_key: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class NaturalCollaborativeNoteCommand:
    user_id: str
    workspace_id: str
    session_id: str
    source_message_id: str
    source_message_text: str
    memory_decision_present: bool
    collaborative_note_decision_present: bool
    artifact_feedback_decision_present: bool
    decision: NaturalCollaborativeNoteDecision
    observed_at: datetime
    accepted_action_index: int | None = None


@dataclass(frozen=True, slots=True)
class CollaborativeNoteDecisionCommand:
    user_id: str
    workspace_id: str
    proposal_id: str
    decision: MemoryDecision
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CollaborativeNoteLifecycleCommand:
    user_id: str
    workspace_id: str
    note_id: str
    expected_revision: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CollaborativeNoteListResult:
    notes: list[CollaborativeNote]
    next_note_id: str | None
    pending_proposals: list[CollaborativeNoteProposal] = field(
        default_factory=list
    )


@dataclass(frozen=True, slots=True)
class CollaborativeNoteDetailResult:
    note: CollaborativeNote
    events: list[CollaborativeNoteEvent]


@dataclass(frozen=True, slots=True)
class CollaborativeNoteProposalResult:
    proposal: CollaborativeNoteProposal
    action: AgentActionReceipt | None = None


@dataclass(frozen=True, slots=True)
class CollaborativeNoteLifecycleResult:
    note: CollaborativeNote
    event: CollaborativeNoteEvent


@dataclass(frozen=True, slots=True)
class CollaborativeNoteDecisionResult:
    action: AgentActionReceipt
    note: CollaborativeNote | None
    event: CollaborativeNoteEvent


@dataclass(frozen=True, slots=True)
class CollaborativeNoteDeletionResult:
    event: CollaborativeNoteEvent


class CollaborativeNoteService:
    def __init__(self, *, database: MemoryEngine) -> None:
        self._database = database

    async def list_notes(
        self,
        command: ListCollaborativeNotesCommand,
    ) -> CollaborativeNoteListResult:
        notes, next_note_id = await self._database.list_collaborative_notes(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            status_filter=command.status_filter,
            limit=command.limit,
            cursor=command.cursor,
        )
        proposals = await self._database.list_collaborative_note_proposals(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            limit=command.limit,
        )
        return CollaborativeNoteListResult(
            notes=list(notes),
            pending_proposals=list(proposals),
            next_note_id=next_note_id,
        )

    async def get_note(
        self,
        command: GetCollaborativeNoteCommand,
    ) -> CollaborativeNoteDetailResult:
        note, events = await self._database.get_collaborative_note_detail(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            note_id=command.note_id,
            limit=command.limit,
        )
        return CollaborativeNoteDetailResult(note=note, events=list(events))

    async def create_correction(
        self,
        command: CollaborativeNoteCorrectionCommand,
    ) -> CollaborativeNoteProposalResult:
        proposal = await self._database.create_collaborative_note_proposal(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            session_id=command.source_session_id,
            source_message_ids=command.source_message_ids,
            note_kind=command.note_kind,
            title=command.title,
            body=command.body,
            idempotency_key=command.idempotency_key,
            expected_note_id=command.note_id,
            expected_revision=command.expected_revision,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteProposalResult(proposal=proposal)

    async def create_proposal(
        self,
        command: CollaborativeNoteProposalCommand,
    ) -> CollaborativeNoteProposalResult:
        source_text = (
            f"Create note proposal: {command.title}\n\n{command.body}"
        )
        source_message_id = await self._database.save_message(
            command.session_id,
            "user",
            source_text,
            project_id=command.workspace_id,
            user_id=command.user_id,
        )
        proposal = await self._database.create_collaborative_note_proposal(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            session_id=command.session_id,
            source_message_ids=(source_message_id,),
            note_kind=command.note_kind,
            title=command.title,
            body=command.body,
            idempotency_key=command.idempotency_key,
            expected_note_id=None,
            expected_revision=None,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteProposalResult(proposal=proposal)

    async def create_natural_proposal(
        self,
        command: NaturalCollaborativeNoteCommand,
    ) -> CollaborativeNoteProposalResult:
        if (
            command.memory_decision_present
            or command.collaborative_note_decision_present
            or command.artifact_feedback_decision_present
        ):
            raise ValueError(
                "Structured decision turns cannot create note proposals."
            )
        if not isinstance(command.decision, NoteCandidateDecision):
            raise ValueError("Command must contain a note candidate.")
        validate_note_candidate_evidence(
            command.decision,
            command.source_message_text,
        )
        idempotency_key = command.source_message_id
        proposal = await self._database.create_collaborative_note_proposal(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            session_id=command.session_id,
            source_message_ids=(command.source_message_id,),
            note_kind=command.decision.note_kind,
            title=command.decision.title,
            body=command.decision.body,
            idempotency_key=idempotency_key,
            expected_note_id=None,
            expected_revision=None,
            observed_at=command.observed_at,
            turn_lease=None,
        )
        return CollaborativeNoteProposalResult(
            proposal=proposal,
            action=AgentActionReceipt(
                action_name="propose_collaborative_note",
                status="completed",
            ),
        )

    async def decide_proposal(
        self,
        command: CollaborativeNoteDecisionCommand,
    ) -> CollaborativeNoteDecisionResult:
        action = AgentActionReceipt(
            action_name=f"{command.decision}_collaborative_note",
            status="completed",
        )
        if command.decision == "approve":
            note, event = await self._database.approve_collaborative_note_proposal(
                user_id=command.user_id,
                workspace_id=command.workspace_id,
                proposal_id=command.proposal_id,
                observed_at=command.observed_at,
            )
            return CollaborativeNoteDecisionResult(
                action=action,
                note=note,
                event=event,
            )
        event = await self._database.reject_collaborative_note_proposal(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            proposal_id=command.proposal_id,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteDecisionResult(
            action=action,
            note=None,
            event=event,
        )

    async def archive_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteLifecycleResult:
        note, event = await self._database.archive_collaborative_note(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            note_id=command.note_id,
            expected_revision=command.expected_revision,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteLifecycleResult(note=note, event=event)

    async def restore_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteLifecycleResult:
        note, event = await self._database.restore_collaborative_note(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            note_id=command.note_id,
            expected_revision=command.expected_revision,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteLifecycleResult(note=note, event=event)

    async def delete_note(
        self,
        command: CollaborativeNoteLifecycleCommand,
    ) -> CollaborativeNoteDeletionResult:
        event = await self._database.delete_collaborative_note(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            note_id=command.note_id,
            expected_revision=command.expected_revision,
            observed_at=command.observed_at,
        )
        return CollaborativeNoteDeletionResult(event=event)
