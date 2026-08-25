from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from zoneinfo import ZoneInfo

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def proposal_payload() -> dict[str, object]:
    return {
        "proposal_id": "proposal-1",
        "note_kind": "decision",
        "title": "  Cafe\u0301   launch  ",
        "body": "  first line\r\nsecond line  ",
        "source_session_id": "session-1",
        "source_message_ids": ["message-1", "message-2"],
        "expected_note_id": None,
        "expected_revision": None,
        "policy_version": "1.0",
        "status": "pending",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
    }


def active_note_payload() -> dict[str, object]:
    return {
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "  macOS only  ",
        "body": "  Preserve\ninternal whitespace.  ",
        "status": "active",
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": NOW,
        "updated_at": NOW,
    }


def test_proposal_serializes_exact_normalized_public_contract() -> None:
    from schemas import CollaborativeNoteProposal

    proposal = CollaborativeNoteProposal.model_validate(proposal_payload())

    assert proposal.model_dump(mode="json") == {
        "proposal_id": "proposal-1",
        "note_kind": "decision",
        "title": "Café launch",
        "body": "first line\nsecond line",
        "source_session_id": "session-1",
        "source_message_ids": ["message-1", "message-2"],
        "expected_note_id": None,
        "expected_revision": None,
        "policy_version": "1.0",
        "status": "pending",
        "created_at": "2026-08-24T12:00:00Z",
        "expires_at": "2026-08-25T12:00:00Z",
    }


def test_active_note_serializes_exact_normalized_public_contract() -> None:
    from schemas import CollaborativeNote

    note = CollaborativeNote.model_validate(active_note_payload())

    assert note.model_dump(mode="json") == {
        "note_id": "note-1",
        "owner_user_id": "user-1",
        "workspace_id": "workspace-1",
        "note_kind": "constraint",
        "title": "macOS only",
        "body": "Preserve\ninternal whitespace.",
        "status": "active",
        "revision": 1,
        "source_session_id": "session-1",
        "source_message_ids": ["message-1"],
        "source_event_id": "event-1",
        "created_at": "2026-08-24T12:00:00Z",
        "updated_at": "2026-08-24T12:00:00Z",
    }


@pytest.mark.parametrize(
    ("model_name", "payload_factory", "field", "value"),
    (
        ("CollaborativeNoteProposal", proposal_payload, "note_kind", "memory"),
        ("CollaborativeNoteProposal", proposal_payload, "status", "active"),
        ("CollaborativeNote", active_note_payload, "note_kind", "profile"),
        ("CollaborativeNote", active_note_payload, "status", "pending"),
    ),
)
def test_note_models_reject_invalid_kind_and_status_vocabularies(
    model_name: str,
    payload_factory: object,
    field: str,
    value: str,
) -> None:
    import schemas

    assert callable(payload_factory)
    payload = payload_factory()
    payload[field] = value
    model = getattr(schemas, model_name)

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("model_name", "payload_factory"),
    (
        ("CollaborativeNoteProposal", proposal_payload),
        ("CollaborativeNote", active_note_payload),
    ),
)
def test_note_models_reject_unknown_fields(
    model_name: str,
    payload_factory: object,
) -> None:
    import schemas

    assert callable(payload_factory)
    payload = payload_factory()
    payload["note_contract_version"] = "1.0"
    model = getattr(schemas, model_name)

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("version", (None, "1.1", 1, True))
def test_proposal_requires_supported_policy_version(version: object) -> None:
    from schemas import CollaborativeNoteProposal

    payload = proposal_payload()
    if version is None:
        del payload["policy_version"]
    else:
        payload["policy_version"] = version

    with pytest.raises(ValidationError):
        CollaborativeNoteProposal.model_validate(payload)


@pytest.mark.parametrize("count", (0, 1, 5, 6))
def test_note_models_enforce_source_message_count(count: int) -> None:
    from schemas import CollaborativeNoteProposal

    payload = proposal_payload()
    payload["source_message_ids"] = [f"message-{index}" for index in range(count)]

    if 1 <= count <= 5:
        assert CollaborativeNoteProposal.model_validate(payload).source_message_ids == [
            f"message-{index}" for index in range(count)
        ]
    else:
        with pytest.raises(ValidationError):
            CollaborativeNoteProposal.model_validate(payload)


def test_note_models_reject_source_message_ids_that_duplicate_after_normalization() -> None:
    from schemas import CollaborativeNote

    payload = active_note_payload()
    payload["source_message_ids"] = [" message-1 ", "message-1"]

    with pytest.raises(ValidationError):
        CollaborativeNote.model_validate(payload)


@pytest.mark.parametrize(
    ("expected_note_id", "expected_revision", "is_valid"),
    (
        (None, None, True),
        ("note-1", 1, True),
        ("note-1", None, False),
        (None, 1, False),
        ("note-1", 0, False),
    ),
)
def test_proposal_requires_paired_expected_note_and_revision(
    expected_note_id: str | None,
    expected_revision: int | None,
    is_valid: bool,
) -> None:
    from schemas import CollaborativeNoteProposal

    payload = proposal_payload()
    payload["expected_note_id"] = expected_note_id
    payload["expected_revision"] = expected_revision

    if is_valid:
        proposal = CollaborativeNoteProposal.model_validate(payload)
        assert proposal.expected_note_id == expected_note_id
        assert proposal.expected_revision == expected_revision
    else:
        with pytest.raises(ValidationError):
            CollaborativeNoteProposal.model_validate(payload)


@pytest.mark.parametrize(
    ("created_at", "expires_at", "is_valid"),
    (
        (datetime(2026, 8, 24, 12, 0), datetime(2026, 8, 25, 12, 0, tzinfo=UTC), False),
        (NOW, NOW - timedelta(hours=24), False),
        (NOW, NOW + timedelta(hours=23), False),
        (NOW, NOW + timedelta(hours=25), False),
        (
            datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            datetime(2026, 8, 25, 8, 0, tzinfo=ZoneInfo("America/New_York")),
            True,
        ),
        (
            datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 11, 1, 23, 30, tzinfo=ZoneInfo("America/New_York")),
            True,
        ),
    ),
)
def test_proposal_requires_aware_exactly_24_elapsed_hours(
    created_at: datetime,
    expires_at: datetime,
    is_valid: bool,
) -> None:
    from schemas import CollaborativeNoteProposal

    payload = proposal_payload()
    payload["created_at"] = created_at
    payload["expires_at"] = expires_at

    if is_valid:
        assert CollaborativeNoteProposal.model_validate(payload).expires_at == expires_at
    else:
        with pytest.raises(ValidationError):
            CollaborativeNoteProposal.model_validate(payload)


@pytest.mark.parametrize(
    ("created_at", "updated_at", "is_valid"),
    (
        (datetime(2026, 8, 24, 12, 0), NOW, False),
        (NOW, NOW - timedelta(seconds=1), False),
        (
            datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 8, 0, tzinfo=ZoneInfo("America/New_York")),
            True,
        ),
    ),
)
def test_active_note_requires_aware_nonreversed_elapsed_timestamps(
    created_at: datetime,
    updated_at: datetime,
    is_valid: bool,
) -> None:
    from schemas import CollaborativeNote

    payload = active_note_payload()
    payload["created_at"] = created_at
    payload["updated_at"] = updated_at

    if is_valid:
        assert CollaborativeNote.model_validate(payload).updated_at == updated_at
    else:
        with pytest.raises(ValidationError):
            CollaborativeNote.model_validate(payload)


@pytest.mark.parametrize("value", (True, "1"))
def test_proposal_rejects_coercible_noninteger_expected_revision(
    value: object,
) -> None:
    from schemas import CollaborativeNoteProposal

    payload = proposal_payload()
    payload["expected_note_id"] = "note-1"
    payload["expected_revision"] = value

    with pytest.raises(ValidationError):
        CollaborativeNoteProposal.model_validate(payload)


@pytest.mark.parametrize("value", (True, "1"))
def test_active_note_rejects_coercible_noninteger_revision(value: object) -> None:
    from schemas import CollaborativeNote

    payload = active_note_payload()
    payload["revision"] = value

    with pytest.raises(ValidationError):
        CollaborativeNote.model_validate(payload)


def test_note_models_retain_actual_integer_revision_behavior() -> None:
    from schemas import CollaborativeNote, CollaborativeNoteProposal

    proposal = proposal_payload()
    proposal["expected_note_id"] = "note-1"
    proposal["expected_revision"] = 2
    note = active_note_payload()
    note["revision"] = 2

    assert CollaborativeNoteProposal.model_validate(proposal).expected_revision == 2
    assert CollaborativeNote.model_validate(note).revision == 2
