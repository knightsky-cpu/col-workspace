import pytest
from pydantic import TypeAdapter, ValidationError


def test_profile_candidate_requires_one_canonical_v2_value() -> None:
    from memory_candidate_decisions import (
        NaturalMemoryDecision,
        ProfileCandidateDecision,
    )

    decision = TypeAdapter(NaturalMemoryDecision).validate_python(
        {
            "kind": "profile_candidate",
            "category": "development_environments",
            "canonical_value": ["macos", "linux"],
            "evidence_text": "macOS and Linux development environments",
        }
    )

    assert isinstance(decision, ProfileCandidateDecision)
    assert decision.canonical_value == ["macos", "linux"]

    with pytest.raises(ValidationError):
        TypeAdapter(NaturalMemoryDecision).validate_python(
            {
                "kind": "profile_candidate",
                "category": "development_environments",
                "canonical_value": ["freebsd"],
                "evidence_text": "FreeBSD",
            }
        )


def test_decision_variants_reject_unowned_reason_codes_and_extra_fields() -> None:
    from memory_candidate_decisions import NaturalMemoryDecision

    adapter = TypeAdapter(NaturalMemoryDecision)
    assert adapter.validate_python({"kind": "no_memory"}).kind == "no_memory"
    assert adapter.validate_python(
        {"kind": "session_only", "scope": "active_chat"}
    ).scope == "active_chat"
    assert adapter.validate_python(
        {"kind": "workspace_note"}
    ).kind == "workspace_note"
    assert adapter.validate_python(
        {"kind": "unsupported", "reason_code": "unsupported_duration"}
    ).reason_code == "unsupported_duration"
    assert adapter.validate_python(
        {"kind": "prohibited", "reason_code": "credential_or_secret"}
    ).reason_code == "credential_or_secret"

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "unsupported", "reason_code": "model_explanation"}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "no_memory", "rationale": "none"})


def test_clarify_requires_two_to_five_unique_canonical_candidates() -> None:
    from memory_candidate_decisions import ClarifyDecision

    first = {
        "kind": "profile_candidate",
        "category": "preferred_name",
        "canonical_value": "wifiknight",
        "evidence_text": "called wifiknight",
    }
    second = {
        "kind": "profile_candidate",
        "category": "development_environments",
        "canonical_value": ["macos", "linux"],
        "evidence_text": "macOS and Linux",
    }

    decision = ClarifyDecision(candidates=[first, second])
    assert [candidate.category for candidate in decision.candidates] == [
        "preferred_name",
        "development_environments",
    ]

    with pytest.raises(ValidationError):
        ClarifyDecision(candidates=[first])
    with pytest.raises(ValidationError, match="unique"):
        ClarifyDecision(candidates=[first, first])


def test_evidence_must_be_an_exact_case_sensitive_source_substring() -> None:
    from memory_candidate_decisions import (
        ClarifyDecision,
        ProfileCandidateDecision,
        validate_decision_evidence,
    )

    message = (
        "Please remember that I prefer macOS and Linux environments, and "
        "call me wifiknight."
    )
    candidate = ProfileCandidateDecision(
        category="development_environments",
        canonical_value=["macos", "linux"],
        evidence_text="macOS and Linux environments",
    )
    validate_decision_evidence(candidate, message)

    wrong_case = candidate.model_copy(
        update={"evidence_text": "MacOS and Linux environments"}
    )
    with pytest.raises(ValueError, match="exact substring"):
        validate_decision_evidence(wrong_case, message)

    clarify = ClarifyDecision(
        candidates=[
            candidate,
            ProfileCandidateDecision(
                category="preferred_name",
                canonical_value="wifiknight",
                evidence_text="call me wifiknight",
            ),
        ]
    )
    validate_decision_evidence(clarify, message)


def test_preferred_name_must_be_grounded_in_its_evidence_span() -> None:
    from memory_candidate_decisions import (
        ProfileCandidateDecision,
        validate_decision_evidence,
    )

    mismatched = ProfileCandidateDecision(
        category="preferred_name",
        canonical_value="Alice",
        evidence_text="call me Bob",
    )

    with pytest.raises(ValueError, match="absent from the current message"):
        validate_decision_evidence(mismatched, "Please call me Bob.")

    grounded = mismatched.model_copy(
        update={
            "canonical_value": "Bob",
            "evidence_text": "call me Bob",
        }
    )
    validate_decision_evidence(grounded, "Please call me Bob.")


def test_evidence_preserves_whitespace_and_caps_unicode_scalars() -> None:
    from memory_candidate_decisions import ProfileCandidateDecision

    decision = ProfileCandidateDecision(
        category="response_length",
        canonical_value="detailed",
        evidence_text=" detailed answers ",
    )
    assert decision.evidence_text == " detailed answers "

    with pytest.raises(ValidationError):
        ProfileCandidateDecision(
            category="response_length",
            canonical_value="detailed",
            evidence_text="x" * 501,
        )
