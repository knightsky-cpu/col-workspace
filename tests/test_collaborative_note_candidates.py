import pytest
from pydantic import TypeAdapter, ValidationError


def test_note_candidate_accepts_benign_grounded_workspace_note() -> None:
    from collaborative_note_candidates import (
        NaturalCollaborativeNoteDecision,
        NoteCandidateDecision,
        validate_note_candidate_evidence,
    )

    message = "Agent Col, note that this workspace must use API version 2."
    decision = TypeAdapter(NaturalCollaborativeNoteDecision).validate_python(
        {
            "kind": "note_candidate",
            "note_kind": "constraint",
            "title": "API version",
            "body": "This workspace must use API version 2.",
            "evidence_text": "this workspace must use API version 2",
        }
    )

    assert isinstance(decision, NoteCandidateDecision)
    assert decision.note_kind == "constraint"
    assert decision.title == "API version"
    assert decision.body == "This workspace must use API version 2."
    validate_note_candidate_evidence(decision, message)


def test_note_candidate_rejects_extra_fields_and_unknown_kinds() -> None:
    from collaborative_note_candidates import NaturalCollaborativeNoteDecision

    adapter = TypeAdapter(NaturalCollaborativeNoteDecision)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "kind": "note_candidate",
                "note_kind": "memory",
                "title": "API version",
                "body": "Use API version 2.",
                "evidence_text": "Use API version 2",
            }
        )
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "no_note", "reason": "none"})


@pytest.mark.parametrize(
    "body",
    (
        "The API key is sk-123456789abcdef",
        "The test contact email is person@example.com",
        "The office address is 123 Main Street",
        "Note everything the user says",
    ),
)
def test_note_candidate_rejects_unsafe_storage_content(body: str) -> None:
    from collaborative_note_candidates import NoteCandidateDecision

    with pytest.raises(ValidationError):
        NoteCandidateDecision(
            note_kind="working_context",
            title="Unsafe note",
            body=body,
            evidence_text=body,
        )


def test_note_candidate_evidence_must_be_exact_current_message_substring() -> None:
    from collaborative_note_candidates import (
        NoteCandidateDecision,
        validate_note_candidate_evidence,
    )

    decision = NoteCandidateDecision(
        note_kind="working_context",
        title="API version",
        body="Use API version 2.",
        evidence_text="Use API version 2",
    )

    validate_note_candidate_evidence(
        decision,
        "Please note: Use API version 2 for this workspace.",
    )
    with pytest.raises(ValueError, match="exact substring"):
        validate_note_candidate_evidence(
            decision,
            "Please note: use API version 2 for this workspace.",
        )


def test_no_effect_decisions_are_strict_and_parseable() -> None:
    from collaborative_note_candidates import NaturalCollaborativeNoteDecision

    adapter = TypeAdapter(NaturalCollaborativeNoteDecision)

    assert adapter.validate_python({"kind": "no_note"}).kind == "no_note"
    assert adapter.validate_python(
        {"kind": "prohibited", "reason_code": "credential_or_secret"}
    ).reason_code == "credential_or_secret"

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "prohibited", "reason_code": "unsupported_category"}
        )
