from datetime import UTC, datetime

import pytest

from continuity import ContinuitySelectionRequest
from continuity_service import (
    ContinuityResolutionCommand,
    ContinuityService,
)
from schemas import CollaborativeNote


NOW = datetime(2026, 8, 26, 18, 30, tzinfo=UTC)


def active_note(
    note_id: str,
    title: str,
    body: str,
    *,
    status: str = "active",
    workspace_id: str = "workspace-1",
) -> CollaborativeNote:
    return CollaborativeNote(
        note_id=note_id,
        owner_user_id="user-1",
        workspace_id=workspace_id,
        note_kind="constraint",
        title=title,
        body=body,
        status=status,
        revision=2,
        source_session_id="session-1",
        source_message_ids=["message-1"],
        source_event_id=f"{note_id}--approved",
        created_at=NOW,
        updated_at=NOW,
    )


class FakeContinuityStore:
    def __init__(self, notes: tuple[CollaborativeNote, ...]) -> None:
        self.notes = notes
        self.calls: list[tuple[str, str, int]] = []

    async def list_active_collaborative_notes_for_continuity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int,
    ) -> tuple[CollaborativeNote, ...]:
        self.calls.append((user_id, workspace_id, limit))
        return tuple(
            note
            for note in self.notes
            if note.owner_user_id == user_id
            and note.workspace_id == workspace_id
            and note.status == "active"
        )[:limit]


@pytest.mark.asyncio
async def test_resolver_does_not_read_notes_without_explicit_prior_reference() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export and require a preview step.",
            ),
        )
    )
    service = ContinuityService(note_reader=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            message="Please explain export formats.",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []
    assert result.source_texts == []
    assert store.calls == []


@pytest.mark.asyncio
async def test_resolver_returns_exact_title_match_with_body_context_and_receipt() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export and require a preview step.",
            ),
        )
    )
    service = ContinuityService(note_reader=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            message="What did we decide for Export workflow requirements?",
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].model_dump(mode="json") == {
        "receipt_id": "continuity--note-1--rev-2",
        "source_kind": "collaborative_note",
        "source_id": "note-1",
        "display_label": "Used note: Export workflow requirements",
        "match_reason": "exact_title",
        "source_updated_at": "2026-08-26T18:30:00Z",
    }
    assert result.source_texts[0].body == (
        "Use CSV export and require a preview step."
    )
    assert result.choices == []


@pytest.mark.asyncio
async def test_resolver_returns_ambiguous_choices_without_note_bodies() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
            ),
            active_note(
                "note-2",
                "Export workflow constraints",
                "Require a preview step.",
            ),
        )
    )
    service = ContinuityService(note_reader=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            message="What were the export workflow notes?",
        )
    )

    assert result.status == "ambiguous"
    assert [choice.source_id for choice in result.choices] == [
        "note-1",
        "note-2",
    ]
    assert [choice.display_label for choice in result.choices] == [
        "Export workflow requirements",
        "Export workflow constraints",
    ]
    assert result.receipts == []
    assert result.source_texts == []
    assert "CSV export" not in str(result.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_resolver_excludes_archived_notes_from_implicit_match() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
                status="archived",
            ),
        )
    )
    service = ContinuityService(note_reader=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            message="What did we decide for Export workflow requirements?",
        )
    )

    assert result.status == "none"
    assert result.receipts == []
    assert result.choices == []


@pytest.mark.asyncio
async def test_resolver_uses_server_selected_note_without_trusting_body() -> None:
    store = FakeContinuityStore(
        (
            active_note(
                "note-1",
                "Export workflow requirements",
                "Use CSV export.",
            ),
            active_note(
                "note-2",
                "Export workflow constraints",
                "Require a preview step.",
            ),
        )
    )
    service = ContinuityService(note_reader=store)

    result = await service.resolve(
        ContinuityResolutionCommand(
            user_id="user-1",
            workspace_id="workspace-1",
            message="Use the selected note.",
            selection=ContinuitySelectionRequest(
                choice_id="choice-2",
                source_kind="collaborative_note",
                source_id="note-2",
            ),
        )
    )

    assert result.status == "resolved"
    assert result.receipts[0].source_id == "note-2"
    assert result.receipts[0].match_reason == "user_selected"
    assert result.source_texts[0].body == "Require a preview step."
