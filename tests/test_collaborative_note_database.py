from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, call

import pytest

from database import MemoryEngine


NOW = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)


def install_transaction_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_without_sdk_retry(callback):
        async def run(transaction, *args, **kwargs):
            return await callback(transaction, *args, **kwargs)

        return run

    monkeypatch.setattr(
        "database.firestore.async_transactional",
        run_without_sdk_retry,
    )


def snapshot(
    *, exists: bool, data: dict[str, object] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(exists=exists, to_dict=lambda: data)


class AsyncSnapshots:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = documents

    def __aiter__(self):
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self):
        try:
            return snapshot(exists=True, data=next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class NoteStore:
    def __init__(self) -> None:
        self.client = MagicMock()
        self.users = MagicMock()
        self.user_ref = MagicMock()
        self.workspaces = MagicMock()
        self.workspace_ref = MagicMock()
        self.proposals = MagicMock()
        self.proposal_ref = MagicMock()
        self.notes = MagicMock()
        self.note_ref = MagicMock()
        self.events = MagicMock()
        self.event_ref = MagicMock()
        self.sessions = MagicMock()
        self.session_ref = MagicMock()
        self.messages = MagicMock()
        self.message_ref = MagicMock()
        self.turns = MagicMock()
        self.turn_ref = MagicMock()
        self.transaction = MagicMock()

        def root_collection(name: str) -> MagicMock:
            if name == "users":
                return self.users
            if name == "sessions":
                return self.sessions
            raise AssertionError(f"Unexpected root collection: {name}")

        def user_collection(name: str) -> MagicMock:
            if name == "workspaces":
                return self.workspaces
            raise AssertionError(f"Unexpected user collection: {name}")

        def workspace_collection(name: str) -> MagicMock:
            if name == "note_proposals":
                return self.proposals
            if name == "collaborative_notes":
                return self.notes
            raise AssertionError(f"Unexpected workspace collection: {name}")

        def session_collection(name: str) -> MagicMock:
            if name == "messages":
                return self.messages
            if name == "turns":
                return self.turns
            raise AssertionError(f"Unexpected session collection: {name}")

        def note_collection(name: str) -> MagicMock:
            if name == "events":
                return self.events
            raise AssertionError(f"Unexpected note collection: {name}")

        self.client.collection.side_effect = root_collection
        self.client.transaction.return_value = self.transaction
        self.users.document.return_value = self.user_ref
        self.user_ref.collection.side_effect = user_collection
        self.workspaces.document.return_value = self.workspace_ref
        self.workspace_ref.collection.side_effect = workspace_collection
        self.proposals.document.return_value = self.proposal_ref
        self.notes.document.return_value = self.note_ref
        self.proposals.where.return_value.limit.return_value.stream.return_value = (
            AsyncSnapshots([])
        )
        self.notes.where.return_value.limit.return_value.stream.return_value = (
            AsyncSnapshots([])
        )
        self.events.limit.return_value.stream.return_value = AsyncSnapshots([])
        self.note_ref.collection.side_effect = note_collection
        self.events.document.return_value = self.event_ref
        self.sessions.document.return_value = self.session_ref
        self.session_ref.collection.side_effect = session_collection
        self.messages.document.return_value = self.message_ref
        self.turns.document.return_value = self.turn_ref

        self.session_ref.get = AsyncMock(
            return_value=snapshot(
                exists=True,
                data={"user_id": "user-1", "project_id": "workspace-1"},
            )
        )
        self.message_ref.get = AsyncMock(return_value=snapshot(exists=True, data={}))
        self.turn_ref.get = AsyncMock(
            return_value=snapshot(
                exists=True,
                data={
                    "schema_version": "1.0",
                    "status": "in_progress",
                    "user_id": "user-1",
                    "project_id": "workspace-1",
                    "session_id": "session-1",
                    "user_message_id": "message-1",
                    "lease_owner": "owner-token-1",
                    "lease_expires_at": NOW + timedelta(minutes=5),
                    "actions": [],
                    "memory_proposals": [],
                    "artifacts": [],
                    "artifact_feedback": [],
                    "memory_clarifications": [],
                    "collaborative_note_proposals": [],
                    "collaborative_note_events": [],
                },
            )
        )


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_persists_owned_source_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.proposal_ref.get = AsyncMock(return_value=snapshot(exists=False))
    engine = MemoryEngine(store.client)

    proposal = await engine.create_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
        observed_at=NOW,
    )

    assert proposal.status == "pending"
    assert proposal.note_contract_version == "1.0"
    assert proposal.source_message_ids == ["message-1"]
    store.session_ref.get.assert_awaited_once_with(transaction=store.transaction)
    store.message_ref.get.assert_awaited_once_with(transaction=store.transaction)
    store.proposal_ref.get.assert_awaited_once_with(transaction=store.transaction)
    store.transaction.set.assert_called_once_with(
        store.proposal_ref,
        proposal.model_dump(mode="python"),
    )


@pytest.mark.asyncio
async def test_list_active_collaborative_notes_for_continuity_returns_owned_active_notes() -> None:
    store = NoteStore()
    active = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "Export workflow requirements",
        "body": "Use CSV export.",
        "status": "active",
        "revision": 2,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "note-1--approved",
        "created_at": NOW,
        "updated_at": NOW + timedelta(minutes=1),
    }
    store.notes.where.return_value.limit.return_value.stream.return_value = (
        AsyncSnapshots([active])
    )

    notes = await MemoryEngine(
        store.client
    ).list_active_collaborative_notes_for_continuity(
        user_id="user-1",
        workspace_id="workspace-1",
        limit=4,
    )

    assert len(notes) == 1
    assert notes[0].note_id == "note-1"
    assert notes[0].status == "active"
    store.notes.where.assert_called_once_with("status", "==", "active")
    store.notes.where.return_value.limit.assert_called_once_with(4)


@pytest.mark.asyncio
async def test_list_active_collaborative_notes_for_continuity_rejects_cross_scope_record() -> None:
    store = NoteStore()
    cross_scope = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "other-user",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "Export workflow requirements",
        "body": "Use CSV export.",
        "status": "active",
        "revision": 2,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "note-1--approved",
        "created_at": NOW,
        "updated_at": NOW + timedelta(minutes=1),
    }
    store.notes.where.return_value.limit.return_value.stream.return_value = (
        AsyncSnapshots([cross_scope])
    )

    with pytest.raises(ValueError, match="ownership"):
        await MemoryEngine(
            store.client
        ).list_active_collaborative_notes_for_continuity(
            user_id="user-1",
            workspace_id="workspace-1",
            limit=4,
        )


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_records_owned_turn_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memory_proposals import ProposalTurnLease

    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.proposal_ref.get = AsyncMock(return_value=snapshot(exists=False))
    engine = MemoryEngine(store.client)

    proposal = await engine.create_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-token-1",
        ),
    )

    store.turn_ref.get.assert_awaited_once_with(transaction=store.transaction)
    store.transaction.set.assert_has_calls(
        [
            call(store.proposal_ref, proposal.model_dump(mode="python")),
            call(
                store.turn_ref,
                {
                    "actions": [
                        {
                            "action_name": "propose_collaborative_note",
                            "status": "completed",
                        }
                    ],
                    "collaborative_note_proposals": [
                        proposal.model_dump(mode="python")
                    ],
                    "updated_at": ANY,
                },
                merge=True,
            ),
        ],
        any_order=False,
    )


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_records_owned_turn_effect_without_embedded_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memory_proposals import ProposalTurnLease

    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.proposal_ref.get = AsyncMock(return_value=snapshot(exists=False))
    turn_data = store.turn_ref.get.return_value.to_dict().copy()
    turn_data.pop("session_id")
    store.turn_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=turn_data)
    )
    engine = MemoryEngine(store.client)

    proposal = await engine.create_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
        observed_at=NOW,
        turn_lease=ProposalTurnLease(
            turn_id="a" * 64,
            owner_token="owner-token-1",
        ),
    )

    store.transaction.set.assert_has_calls(
        [
            call(store.proposal_ref, proposal.model_dump(mode="python")),
            call(
                store.turn_ref,
                {
                    "actions": [
                        {
                            "action_name": "propose_collaborative_note",
                            "status": "completed",
                        }
                    ],
                    "collaborative_note_proposals": [
                        proposal.model_dump(mode="python")
                    ],
                    "updated_at": ANY,
                },
                merge=True,
            ),
        ],
        any_order=False,
    )


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_rejects_cross_workspace_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.session_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={"user_id": "user-1", "project_id": "other-workspace"},
        )
    )
    engine = MemoryEngine(store.client)

    with pytest.raises(Exception, match="unavailable"):
        await engine.create_collaborative_note_proposal(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-1",
            source_message_ids=("message-1",),
            note_kind="constraint",
            title="API version",
            body="Use API version 2.",
            idempotency_key="idem-1",
            expected_note_id=None,
            expected_revision=None,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_returns_existing_exact_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.proposal_ref.get = AsyncMock(return_value=snapshot(exists=False))
    engine = MemoryEngine(store.client)
    first = await engine.create_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
        observed_at=NOW + timedelta(minutes=5),
    )
    store.transaction.set.reset_mock()
    store.proposal_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=first.model_dump(mode="python"))
    )

    second = await engine.create_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
        observed_at=NOW + timedelta(minutes=5),
    )

    assert second == first
    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_create_collaborative_note_proposal_enforces_pending_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    store.proposal_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.proposals.where.return_value.limit.return_value.stream.return_value = (
        AsyncSnapshots([{"proposal_id": f"proposal-{index}"} for index in range(10)])
    )
    engine = MemoryEngine(store.client)

    with pytest.raises(Exception, match="limit"):
        await engine.create_collaborative_note_proposal(
            user_id="user-1",
            workspace_id="workspace-1",
            session_id="session-1",
            source_message_ids=("message-1",),
            note_kind="constraint",
            title="API version",
            body="Use API version 2.",
            idempotency_key="idem-1",
            expected_note_id=None,
            expected_revision=None,
            observed_at=NOW,
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_collaborative_note_proposal_creates_active_note_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    from schemas import CollaborativeNoteProposal

    proposal = CollaborativeNoteProposal(
        proposal_id="note_proposal--1",
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        source_session_id="session-1",
        source_message_ids=["message-1"],
        expected_note_id=None,
        expected_revision=None,
        policy_version="1.0",
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    store.proposal_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal.model_dump(mode="python"))
    )
    store.note_ref.get = AsyncMock(return_value=snapshot(exists=False))
    engine = MemoryEngine(store.client)

    note, event = await engine.approve_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        proposal_id=proposal.proposal_id,
        observed_at=NOW + timedelta(minutes=1),
    )

    assert note.status == "active"
    assert note.revision == 1
    assert event.event_type == "approved"
    assert event.title == "API version"
    assert store.transaction.set.call_args_list[-3:] == [
        call(
            store.proposal_ref,
            {
                **proposal.model_dump(mode="python"),
                "status": "approved",
                "resolved_at": NOW + timedelta(minutes=1),
            },
            merge=False,
        ),
        call(store.note_ref, note.model_dump(mode="python"), merge=False),
        call(store.event_ref, event.model_dump(mode="python"), merge=False),
    ]


@pytest.mark.asyncio
async def test_approve_new_collaborative_note_enforces_active_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    from schemas import CollaborativeNoteProposal

    proposal = CollaborativeNoteProposal(
        proposal_id="note_proposal--1",
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        source_session_id="session-1",
        source_message_ids=["message-1"],
        expected_note_id=None,
        expected_revision=None,
        policy_version="1.0",
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    store.proposal_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal.model_dump(mode="python"))
    )
    store.note_ref.get = AsyncMock(return_value=snapshot(exists=False))
    store.notes.where.return_value.limit.return_value.stream.return_value = (
        AsyncSnapshots([{"note_id": f"note-{index}"} for index in range(50)])
    )
    engine = MemoryEngine(store.client)

    with pytest.raises(Exception, match="limit"):
        await engine.approve_collaborative_note_proposal(
            user_id="user-1",
            workspace_id="workspace-1",
            proposal_id=proposal.proposal_id,
            observed_at=NOW + timedelta(minutes=1),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_approve_collaborative_note_correction_rejects_stale_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    from schemas import CollaborativeNoteProposal

    proposal = CollaborativeNoteProposal(
        proposal_id="note_proposal--1",
        note_kind="constraint",
        title="API version",
        body="Use API version 3.",
        source_session_id="session-1",
        source_message_ids=["message-1"],
        expected_note_id="note-1",
        expected_revision=1,
        policy_version="1.0",
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    store.proposal_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal.model_dump(mode="python"))
    )
    store.note_ref.get = AsyncMock(
        return_value=snapshot(
            exists=True,
            data={
                "note_contract_version": "1.0",
                "note_id": "note-1",
                "owner_user_id": "user-1",
                "workspace_id": "workspace-1",
                "note_kind": "constraint",
                "title": "API version",
                "body": "Use API version 2.",
                "status": "active",
                "revision": 2,
                "source_session_id": "session-1",
                "source_message_ids": ["message-1"],
                "source_event_id": "event-1",
                "created_at": NOW,
                "updated_at": NOW,
            },
        )
    )
    engine = MemoryEngine(store.client)

    with pytest.raises(Exception, match="revision"):
        await engine.approve_collaborative_note_proposal(
            user_id="user-1",
            workspace_id="workspace-1",
            proposal_id=proposal.proposal_id,
            observed_at=NOW + timedelta(minutes=1),
        )

    store.transaction.set.assert_not_called()


@pytest.mark.asyncio
async def test_reject_collaborative_note_proposal_resolves_without_active_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    from schemas import CollaborativeNoteProposal

    proposal = CollaborativeNoteProposal(
        proposal_id="note_proposal--1",
        note_kind="constraint",
        title="API version",
        body="Use API version 2.",
        source_session_id="session-1",
        source_message_ids=["message-1"],
        expected_note_id=None,
        expected_revision=None,
        policy_version="1.0",
        status="pending",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    store.proposal_ref.get = AsyncMock(
        return_value=snapshot(exists=True, data=proposal.model_dump(mode="python"))
    )
    engine = MemoryEngine(store.client)

    event = await engine.reject_collaborative_note_proposal(
        user_id="user-1",
        workspace_id="workspace-1",
        proposal_id=proposal.proposal_id,
        observed_at=NOW + timedelta(minutes=1),
    )

    assert event.event_type == "rejected"
    assert event.proposal_id == proposal.proposal_id
    assert event.title is None
    assert event.body is None
    store.note_ref.get.assert_not_called()
    store.transaction.set.assert_has_calls(
        [
            call(
                store.proposal_ref,
                {
                    **proposal.model_dump(mode="python"),
                    "status": "rejected",
                    "resolved_at": NOW + timedelta(minutes=1),
                },
                merge=False,
            ),
            call(store.event_ref, event.model_dump(mode="python"), merge=False),
        ]
    )


@pytest.mark.parametrize(
    ("method_name", "starting_status", "ending_status", "event_type"),
    (
        ("archive_collaborative_note", "active", "archived", "archived"),
        ("restore_collaborative_note", "archived", "active", "restored"),
    ),
)
@pytest.mark.asyncio
async def test_archive_and_restore_collaborative_note_write_revisioned_event(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    starting_status: str,
    ending_status: str,
    event_type: str,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    note = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": starting_status,
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    store.note_ref.get = AsyncMock(return_value=snapshot(exists=True, data=note))
    engine = MemoryEngine(store.client)

    updated, event = await getattr(engine, method_name)(
        user_id="user-1",
        workspace_id="workspace-1",
        note_id="note-1",
        expected_revision=1,
        observed_at=NOW + timedelta(minutes=2),
    )

    assert updated.status == ending_status
    assert updated.revision == 2
    assert event.event_type == event_type
    assert event.previous_revision == 1
    store.transaction.set.assert_has_calls(
        [
            call(store.note_ref, updated.model_dump(mode="python"), merge=False),
            call(store.event_ref, event.model_dump(mode="python"), merge=False),
        ]
    )


@pytest.mark.asyncio
async def test_delete_collaborative_note_removes_active_content_and_keeps_safe_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transaction_runner(monkeypatch)
    store = NoteStore()
    note = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": "active",
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    store.note_ref.get = AsyncMock(return_value=snapshot(exists=True, data=note))
    engine = MemoryEngine(store.client)

    event = await engine.delete_collaborative_note(
        user_id="user-1",
        workspace_id="workspace-1",
        note_id="note-1",
        expected_revision=1,
        observed_at=NOW + timedelta(minutes=2),
    )

    assert event.event_type == "deleted"
    assert event.title is None
    assert event.body is None
    store.transaction.delete.assert_called_once_with(store.note_ref)
    store.transaction.set.assert_called_once_with(
        store.event_ref,
        event.model_dump(mode="python"),
        merge=False,
    )


@pytest.mark.asyncio
async def test_list_collaborative_notes_returns_bounded_workspace_notes() -> None:
    store = NoteStore()
    first = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": "active",
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    second = {**first, "note_id": "note-2", "source_event_id": "event-2"}
    store.notes.where.return_value.limit.return_value.stream.return_value = (
        AsyncSnapshots([first, second])
    )
    engine = MemoryEngine(store.client)

    notes, next_note_id = await engine.list_collaborative_notes(
        user_id="user-1",
        workspace_id="workspace-1",
        status_filter="active",
        limit=1,
        cursor=None,
    )

    assert [note.note_id for note in notes] == ["note-1"]
    assert next_note_id == "note-2"
    store.notes.where.assert_called_once_with("status", "==", "active")
    store.notes.where.return_value.limit.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_get_collaborative_note_detail_returns_note_and_safe_events() -> None:
    store = NoteStore()
    note = {
        "note_contract_version": "1.0",
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "status": "active",
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    event = {
        "note_contract_version": "1.0",
        "event_id": "event-1",
        "note_id": "note-1",
        "proposal_id": "proposal-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "event_type": "approved",
        "note_kind": "constraint",
        "title": "API version",
        "body": "Use API version 2.",
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "revision": 1,
        "previous_revision": None,
        "created_at": NOW,
    }
    store.note_ref.get = AsyncMock(return_value=snapshot(exists=True, data=note))
    store.events.limit.return_value.stream.return_value = AsyncSnapshots([event])
    engine = MemoryEngine(store.client)

    stored_note, events = await engine.get_collaborative_note_detail(
        user_id="user-1",
        workspace_id="workspace-1",
        note_id="note-1",
        limit=10,
    )

    assert stored_note.note_id == "note-1"
    assert [item.event_id for item in events] == ["event-1"]
    store.note_ref.get.assert_awaited_once()
    store.events.limit.assert_called_once_with(10)
