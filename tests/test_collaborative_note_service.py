from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from schemas import CollaborativeNote, CollaborativeNoteEvent, CollaborativeNoteProposal


NOW = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)


def note_payload(*, status: str = "active", revision: int = 1) -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": status,
        "revision": revision,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }


def proposal_payload() -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "proposal_id": "note_proposal--1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 3.",
        "source_session_id": "session-2",
        "source_message_ids": ["message-2"],
        "expected_note_id": "note-1",
        "expected_revision": 1,
        "policy_version": "1.0",
        "status": "pending",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
    }


def event_payload(event_type: str = "archived") -> dict[str, object]:
    return {
        "note_contract_version": "1.0",
        "event_id": f"note-1--{event_type}--2",
        "note_id": "note-1",
        "proposal_id": None,
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "event_type": event_type,
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "revision": 2,
        "previous_revision": 1,
        "created_at": NOW,
    }


@dataclass
class FakeNoteDatabase:
    notes: tuple[CollaborativeNote, ...] = field(
        default_factory=lambda: (CollaborativeNote.model_validate(note_payload()),)
    )
    note: CollaborativeNote = field(
        default_factory=lambda: CollaborativeNote.model_validate(note_payload())
    )
    events: tuple[CollaborativeNoteEvent, ...] = field(
        default_factory=lambda: (
            CollaborativeNoteEvent.model_validate(event_payload("archived")),
        )
    )
    proposal: CollaborativeNoteProposal = field(
        default_factory=lambda: CollaborativeNoteProposal.model_validate(
            proposal_payload()
        )
    )
    list_calls: list[dict[str, object]] = field(default_factory=list)
    detail_calls: list[dict[str, object]] = field(default_factory=list)
    proposal_calls: list[dict[str, object]] = field(default_factory=list)
    approve_calls: list[dict[str, object]] = field(default_factory=list)
    reject_calls: list[dict[str, object]] = field(default_factory=list)
    archive_calls: list[dict[str, object]] = field(default_factory=list)
    restore_calls: list[dict[str, object]] = field(default_factory=list)
    delete_calls: list[dict[str, object]] = field(default_factory=list)

    async def list_collaborative_notes(self, **kwargs: object):
        self.list_calls.append(kwargs)
        return self.notes, None

    async def get_collaborative_note_detail(self, **kwargs: object):
        self.detail_calls.append(kwargs)
        return self.note, self.events

    async def create_collaborative_note_proposal(self, **kwargs: object):
        self.proposal_calls.append(kwargs)
        return self.proposal

    async def archive_collaborative_note(self, **kwargs: object):
        self.archive_calls.append(kwargs)
        return self.note.model_copy(update={"status": "archived", "revision": 2}), self.events[0]

    async def approve_collaborative_note_proposal(self, **kwargs: object):
        self.approve_calls.append(kwargs)
        return self.note, CollaborativeNoteEvent.model_validate(
            {
                **event_payload("approved"),
                "proposal_id": "note_proposal--1",
                "previous_revision": None,
            }
        )

    async def reject_collaborative_note_proposal(self, **kwargs: object):
        self.reject_calls.append(kwargs)
        return CollaborativeNoteEvent.model_validate(
            {
                **event_payload("rejected"),
                "proposal_id": "note_proposal--1",
                "note_kind": None,
                "title": None,
                "body": None,
                "source_session_id": None,
                "source_message_ids": [],
            }
        )

    async def restore_collaborative_note(self, **kwargs: object):
        self.restore_calls.append(kwargs)
        return self.note.model_copy(update={"status": "active", "revision": 2}), self.events[0]

    async def delete_collaborative_note(self, **kwargs: object):
        self.delete_calls.append(kwargs)
        return CollaborativeNoteEvent.model_validate(
            {
                **event_payload("deleted"),
                "note_kind": None,
                "title": None,
                "body": None,
                "source_session_id": None,
                "source_message_ids": [],
            }
        )


@pytest.mark.asyncio
async def test_note_service_lists_active_notes_by_default() -> None:
    from collaborative_note_service import (
        CollaborativeNoteService,
        ListCollaborativeNotesCommand,
    )

    database = FakeNoteDatabase()
    service = CollaborativeNoteService(database=database)

    result = await service.list_notes(
        ListCollaborativeNotesCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            status_filter="active",
            limit=20,
            cursor=None,
        )
    )

    assert result.notes == list(database.notes)
    assert database.list_calls == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "status_filter": "active",
            "limit": 20,
            "cursor": None,
        }
    ]


@pytest.mark.asyncio
async def test_note_service_creates_correction_without_mutating_active_note() -> None:
    from collaborative_note_service import (
        CollaborativeNoteCorrectionCommand,
        CollaborativeNoteService,
    )

    database = FakeNoteDatabase()
    service = CollaborativeNoteService(database=database)

    result = await service.create_correction(
        CollaborativeNoteCorrectionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            note_id="note-1",
            expected_revision=1,
            note_kind="constraint",
            title="API version",
            body="Use API version 3.",
            source_session_id="session-2",
            source_message_ids=("message-2",),
            idempotency_key="idem-1",
            observed_at=NOW,
        )
    )

    assert result.proposal.expected_note_id == "note-1"
    assert result.proposal.expected_revision == 1
    assert database.detail_calls == []
    assert database.proposal_calls == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "session_id": "session-2",
            "source_message_ids": ("message-2",),
            "note_kind": "constraint",
            "title": "API version",
            "body": "Use API version 3.",
            "idempotency_key": "idem-1",
            "expected_note_id": "note-1",
            "expected_revision": 1,
            "observed_at": NOW,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ("approve", "reject"))
async def test_note_service_decides_pending_note_proposal(
    decision: str,
) -> None:
    from collaborative_note_service import (
        CollaborativeNoteDecisionCommand,
        CollaborativeNoteDecisionResult,
        CollaborativeNoteService,
    )

    database = FakeNoteDatabase()
    service = CollaborativeNoteService(database=database)

    result = await service.decide_proposal(
        CollaborativeNoteDecisionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            proposal_id="note_proposal--1",
            decision=decision,
            observed_at=NOW,
        )
    )

    assert isinstance(result, CollaborativeNoteDecisionResult)
    assert result.action.action_name == f"{decision}_collaborative_note"
    assert result.event.event_type in {
        "approved" if decision == "approve" else "rejected"
    }
    expected_call = {
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "proposal_id": "note_proposal--1",
        "observed_at": NOW,
    }
    if decision == "approve":
        assert database.approve_calls == [expected_call]
        assert database.reject_calls == []
        assert result.note == database.note
    else:
        assert database.reject_calls == [expected_call]
        assert database.approve_calls == []
        assert result.note is None


@pytest.mark.asyncio
async def test_note_service_reads_detail_without_source_message_text() -> None:
    from collaborative_note_service import (
        CollaborativeNoteService,
        GetCollaborativeNoteCommand,
    )

    database = FakeNoteDatabase()
    service = CollaborativeNoteService(database=database)

    result = await service.get_note(
        GetCollaborativeNoteCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            note_id="note-1",
            limit=10,
        )
    )

    assert result.note == database.note
    assert result.events == list(database.events)
    assert database.detail_calls == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "note_id": "note-1",
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "calls_name", "event_type"),
    [
        ("archive_note", "archive_calls", "archived"),
        ("restore_note", "restore_calls", "archived"),
        ("delete_note", "delete_calls", "deleted"),
    ],
)
async def test_note_service_routes_revisioned_lifecycle_commands(
    method_name: str,
    calls_name: str,
    event_type: str,
) -> None:
    from collaborative_note_service import (
        CollaborativeNoteLifecycleCommand,
        CollaborativeNoteService,
    )

    database = FakeNoteDatabase()
    service = CollaborativeNoteService(database=database)

    result = await getattr(service, method_name)(
        CollaborativeNoteLifecycleCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            note_id="note-1",
            expected_revision=1,
            observed_at=NOW,
        )
    )

    assert result.event.event_type == event_type
    assert getattr(database, calls_name) == [
        {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "note_id": "note-1",
            "expected_revision": 1,
            "observed_at": NOW,
        }
    ]
