from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from pydantic import ValidationError


NOW = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)


class MissingOffsetTimezone(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        return None

    def dst(self, value: datetime | None) -> None:
        return None


def candidate_payloads() -> list[dict[str, object]]:
    return [
        {
            "category": "preferred_name",
            "canonical_value": "wifiknight",
        },
        {
            "category": "development_environments",
            "canonical_value": ["linux", "macos"],
        },
    ]


def open_envelope(**updates: object):
    from memory_clarifications import (
        MemoryClarificationEnvelope,
        derive_memory_clarification_id,
    )

    payload: dict[str, object] = {
        "clarification_id": derive_memory_clarification_id(
            user_id="user-1",
            session_id="session-1",
            evidence_message_id="message-evidence",
            clarification_turn_id="turn-clarify",
        ),
        "user_id": "user-1",
        "session_id": "session-1",
        "workspace_id": "workspace-1",
        "evidence_message_id": "message-evidence",
        "clarification_turn_id": "turn-clarify",
        "candidates": candidate_payloads(),
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
        "status": "open",
        "consuming_turn_id": None,
        "consuming_message_id": None,
        "selected_candidate_index": None,
    }
    payload.update(updates)
    return MemoryClarificationEnvelope.model_validate(payload)


def test_clarification_id_is_deterministic_and_server_owned() -> None:
    from memory_clarifications import derive_memory_clarification_id

    first = derive_memory_clarification_id(
        user_id="user-1",
        session_id="session-1",
        evidence_message_id="message-evidence",
        clarification_turn_id="turn-clarify",
    )
    second = derive_memory_clarification_id(
        user_id="user-1",
        session_id="session-1",
        evidence_message_id="message-evidence",
        clarification_turn_id="turn-clarify",
    )

    assert first == second
    assert first.startswith("memory-clarification--")
    assert len(first.removeprefix("memory-clarification--")) == 64
    assert first != derive_memory_clarification_id(
        user_id="user-2",
        session_id="session-1",
        evidence_message_id="message-evidence",
        clarification_turn_id="turn-clarify",
    )


def test_open_envelope_canonicalizes_candidates_and_enforces_lifetime() -> None:
    envelope = open_envelope()

    assert envelope.clarification_schema_version == "1.0"
    assert envelope.candidates[1].canonical_value == ["macos", "linux"]

    with pytest.raises(ValidationError, match="15 minutes"):
        open_envelope(expires_at=NOW + timedelta(minutes=16))
    with pytest.raises(ValidationError, match="timezone aware"):
        open_envelope(created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError, match="timezone aware"):
        open_envelope(created_at=NOW.replace(tzinfo=MissingOffsetTimezone()))


def test_envelope_requires_unique_candidates_and_state_fields() -> None:
    with pytest.raises(ValidationError, match="unique"):
        open_envelope(candidates=[candidate_payloads()[0]] * 2)

    with pytest.raises(ValidationError, match="Open clarification"):
        open_envelope(consuming_turn_id="turn-select")

    consumed = open_envelope(
        status="consumed",
        consuming_turn_id="turn-select",
        consuming_message_id="message-select",
        selected_candidate_index=1,
    )
    assert consumed.selected_candidate_index == 1

    with pytest.raises(ValidationError, match="selected candidate"):
        open_envelope(
            status="consumed",
            consuming_turn_id="turn-select",
            consuming_message_id="message-select",
            selected_candidate_index=2,
        )

    expired = open_envelope(status="expired")
    assert expired.selected_candidate_index is None


def test_receipt_uses_application_owned_human_labels() -> None:
    from memory_clarifications import clarification_receipt

    receipt = clarification_receipt(open_envelope())

    assert receipt.clarification_id == open_envelope().clarification_id
    assert [choice.model_dump() for choice in receipt.choices] == [
        {
            "candidate_index": 0,
            "category_label": "Preferred name",
            "value_label": "wifiknight",
        },
        {
            "candidate_index": 1,
            "category_label": "Development environments",
            "value_label": "macOS and Linux",
        },
    ]


def test_valid_selection_returns_one_server_owned_candidate() -> None:
    from memory_clarifications import (
        MemoryClarificationSelection,
        validate_memory_clarification_selection,
    )

    candidate = validate_memory_clarification_selection(
        envelope=open_envelope(),
        selection=MemoryClarificationSelection(selected_candidate_index=1),
        user_id="user-1",
        session_id="session-1",
        workspace_id="workspace-1",
        selecting_turn_id="turn-select",
        selecting_message_id="message-select",
        is_first_subsequent_turn=True,
        observed_at=NOW + timedelta(minutes=5),
    )

    assert candidate.category == "development_environments"
    assert candidate.canonical_value == ["macos", "linux"]


@pytest.mark.parametrize(
    ("update", "message"),
    (
        ({"user_id": "user-2"}, "owned"),
        ({"session_id": "session-2"}, "owned"),
        ({"workspace_id": "workspace-2"}, "owned"),
        ({"selecting_turn_id": "turn-clarify"}, "subsequent"),
        ({"selecting_message_id": "message-evidence"}, "subsequent"),
        (
            {
                "observed_at": NOW.replace(
                    tzinfo=MissingOffsetTimezone()
                )
            },
            "timezone aware",
        ),
        ({"observed_at": NOW + timedelta(minutes=16)}, "expired"),
    ),
)
def test_selection_fails_closed_outside_owned_next_turn(
    update: dict[str, object],
    message: str,
) -> None:
    from memory_clarifications import (
        MemoryClarificationSelection,
        validate_memory_clarification_selection,
    )

    kwargs: dict[str, object] = {
        "envelope": open_envelope(),
        "selection": MemoryClarificationSelection(
            selected_candidate_index=0
        ),
        "user_id": "user-1",
        "session_id": "session-1",
        "workspace_id": "workspace-1",
        "selecting_turn_id": "turn-select",
        "selecting_message_id": "message-select",
        "is_first_subsequent_turn": True,
        "observed_at": NOW + timedelta(minutes=5),
    }
    kwargs.update(update)

    with pytest.raises(ValueError, match=message):
        validate_memory_clarification_selection(**kwargs)


def test_selection_rejects_non_open_or_out_of_range_choice() -> None:
    from memory_clarifications import (
        MemoryClarificationSelection,
        validate_memory_clarification_selection,
    )

    with pytest.raises(ValidationError):
        MemoryClarificationSelection(selected_candidate_index=-1)
    with pytest.raises(ValueError, match="open"):
        validate_memory_clarification_selection(
            envelope=open_envelope(status="expired"),
            selection=MemoryClarificationSelection(
                selected_candidate_index=0
            ),
            user_id="user-1",
            session_id="session-1",
            workspace_id="workspace-1",
            selecting_turn_id="turn-select",
            selecting_message_id="message-select",
            is_first_subsequent_turn=True,
            observed_at=NOW + timedelta(minutes=5),
        )


def test_selection_rejects_a_later_turn_after_the_first_subsequent_turn() -> None:
    from memory_clarifications import (
        MemoryClarificationSelection,
        validate_memory_clarification_selection,
    )

    with pytest.raises(ValueError, match="first subsequent user turn"):
        validate_memory_clarification_selection(
            envelope=open_envelope(),
            selection=MemoryClarificationSelection(
                selected_candidate_index=0
            ),
            user_id="user-1",
            session_id="session-1",
            workspace_id="workspace-1",
            selecting_turn_id="turn-later",
            selecting_message_id="message-later",
            is_first_subsequent_turn=False,
            observed_at=NOW + timedelta(minutes=14),
        )
