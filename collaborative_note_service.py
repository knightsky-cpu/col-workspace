from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from database import MemoryEngine
from collaborative_note_policy import CollaborativeNoteKind
from schemas import CollaborativeNote, CollaborativeNoteEvent, CollaborativeNoteProposal

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


@dataclass(frozen=True, slots=True)
class CollaborativeNoteDetailResult:
    note: CollaborativeNote
    events: list[CollaborativeNoteEvent]


@dataclass(frozen=True, slots=True)
class CollaborativeNoteProposalResult:
    proposal: CollaborativeNoteProposal


@dataclass(frozen=True, slots=True)
class CollaborativeNoteLifecycleResult:
    note: CollaborativeNote
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
        return CollaborativeNoteListResult(
            notes=list(notes),
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
