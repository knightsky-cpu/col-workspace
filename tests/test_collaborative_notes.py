from datetime import UTC, datetime


NOW = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)


def test_note_proposal_ids_are_stable_for_exact_retry() -> None:
    from collaborative_notes import derive_note_proposal_ids

    first = derive_note_proposal_ids(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API Version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
    )
    second = derive_note_proposal_ids(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API Version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
    )

    assert second == first
    assert first.proposal_id.startswith("note_proposal--")
    assert first.note_id.startswith("note--")
    assert first.event_id("approved").startswith(f"{first.note_id}--approved--")


def test_note_proposal_ids_change_when_authority_or_content_changes() -> None:
    from collaborative_notes import derive_note_proposal_ids

    baseline = derive_note_proposal_ids(
        user_id="user-1",
        workspace_id="workspace-1",
        session_id="session-1",
        source_message_ids=("message-1",),
        note_kind="constraint",
        title="API Version",
        body="Use API version 2.",
        idempotency_key="idem-1",
        expected_note_id=None,
        expected_revision=None,
    )

    changes = [
        {"user_id": "user-2"},
        {"workspace_id": "workspace-2"},
        {"session_id": "session-2"},
        {"source_message_ids": ("message-2",)},
        {"title": "Runtime Version"},
        {"body": "Use API version 3."},
        {"idempotency_key": "idem-2"},
        {"expected_note_id": "note-existing", "expected_revision": 1},
    ]

    for change in changes:
        request = {
            "user_id": "user-1",
            "workspace_id": "workspace-1",
            "session_id": "session-1",
            "source_message_ids": ("message-1",),
            "note_kind": "constraint",
            "title": "API Version",
            "body": "Use API version 2.",
            "idempotency_key": "idem-1",
            "expected_note_id": None,
            "expected_revision": None,
        }
        request.update(change)

        assert derive_note_proposal_ids(**request) != baseline
