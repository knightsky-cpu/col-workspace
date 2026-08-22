import importlib
from copy import deepcopy

import pytest
from pydantic import ValidationError

from expert_contracts import ExpertCapability, ExpertStatus


def load_requirements_verification():
    try:
        return importlib.import_module("requirements_verification")
    except ModuleNotFoundError:
        pytest.fail("requirements_verification has not been implemented")


def valid_input_payload() -> dict[str, object]:
    return {
        "objective": "Compare the supplied material.",
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "text": "Include sources.",
                "source_block_id": "block-2",
            },
        ],
        "subject_blocks": [
            {
                "subject_block_id": "SUBJECT-001",
                "text": "Two sources are included.",
                "source_block_id": "block-4",
            },
        ],
        "constraints": [],
    }


def test_input_accepts_locally_identified_exact_source_blocks() -> None:
    verification = load_requirements_verification()

    request = verification.RequirementsVerificationInput(
        objective="Compare the subject with every requirement.",
        requirements=(
            {
                "requirement_id": "REQ-001",
                "text": "The response must include sources.",
                "source_block_id": "block-2",
            },
            {
                "requirement_id": "REQ-002",
                "text": "The response must state limitations.",
                "source_block_id": "block-3",
            },
        ),
        subject_blocks=(
            {
                "subject_block_id": "SUBJECT-001",
                "text": "The response cites two sources and states one limitation.",
                "source_block_id": "block-5",
            },
        ),
        constraints=("Use only supplied subject evidence.",),
    )

    assert tuple(item.requirement_id for item in request.requirements) == (
        "REQ-001",
        "REQ-002",
    )
    assert request.requirements[0].text == (
        "The response must include sources."
    )
    assert request.subject_blocks[0].subject_block_id == "SUBJECT-001"
    assert request.subject_blocks[0].source_block_id == "block-5"
    assert request.constraints == ("Use only supplied subject evidence.",)


def test_input_rejects_nonsequential_local_requirement_ids() -> None:
    verification = load_requirements_verification()

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationInput(
            objective="Compare the supplied material.",
            requirements=(
                {
                    "requirement_id": "REQ-002",
                    "text": "Include sources.",
                    "source_block_id": "block-2",
                },
            ),
            subject_blocks=(
                {
                    "subject_block_id": "SUBJECT-001",
                    "text": "Two sources are included.",
                    "source_block_id": "block-4",
                },
            ),
        )


@pytest.mark.parametrize("reversed_collection", ("requirements", "subjects"))
def test_input_rejects_source_blocks_out_of_selected_order(
    reversed_collection: str,
) -> None:
    verification = load_requirements_verification()
    payload = valid_input_payload()
    if reversed_collection == "requirements":
        payload["requirements"] = [
            {
                "requirement_id": "REQ-001",
                "text": "First requirement.",
                "source_block_id": "block-3",
            },
            {
                "requirement_id": "REQ-002",
                "text": "Second requirement.",
                "source_block_id": "block-2",
            },
        ]
    else:
        payload["requirements"][0]["source_block_id"] = "block-1"
        payload["subject_blocks"] = [
            {
                "subject_block_id": "SUBJECT-001",
                "text": "First subject block.",
                "source_block_id": "block-4",
            },
            {
                "subject_block_id": "SUBJECT-002",
                "text": "Second subject block.",
                "source_block_id": "block-3",
            },
        ]

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationInput.model_validate(payload)


def _requirements(count: int, text: str = "Requirement") -> list[dict[str, str]]:
    return [
        {
            "requirement_id": f"REQ-{index:03d}",
            "text": text,
            "source_block_id": f"block-{index}",
        }
        for index in range(1, count + 1)
    ]


def _subjects(count: int, text: str = "Subject") -> list[dict[str, str]]:
    return [
        {
            "subject_block_id": f"SUBJECT-{index:03d}",
            "text": text,
            "source_block_id": f"block-{index + 1}",
        }
        for index in range(1, count + 1)
    ]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(objective="   "),
        lambda payload: payload.update(requirements=[]),
        lambda payload: payload.update(subject_blocks=[]),
        lambda payload: payload.update(
            requirements=_requirements(51),
            subject_blocks=[
                {
                    "subject_block_id": "SUBJECT-001",
                    "text": "Subject",
                    "source_block_id": "block-52",
                }
            ],
        ),
        lambda payload: payload.update(
            requirements=[
                {
                    "requirement_id": "REQ-001",
                    "text": "Requirement",
                    "source_block_id": "block-64",
                }
            ],
            subject_blocks=_subjects(33),
        ),
        lambda payload: payload["subject_blocks"][0].update(
            subject_block_id="SUBJECT-002"
        ),
        lambda payload: payload["subject_blocks"][0].update(
            source_block_id="block-2"
        ),
        lambda payload: payload["requirements"][0].update(text="r" * 1_001),
        lambda payload: payload["subject_blocks"][0].update(text="s" * 8_001),
        lambda payload: payload.update(
            requirements=_requirements(7, "r" * 901),
            subject_blocks=[
                {
                    "subject_block_id": "SUBJECT-001",
                    "text": "Subject",
                    "source_block_id": "block-8",
                }
            ],
        ),
        lambda payload: payload.update(
            requirements=_requirements(1),
            subject_blocks=[
                {
                    "subject_block_id": "SUBJECT-001",
                    "text": "s" * 4_001,
                    "source_block_id": "block-2",
                },
                {
                    "subject_block_id": "SUBJECT-002",
                    "text": "s" * 4_001,
                    "source_block_id": "block-3",
                },
            ],
        ),
        lambda payload: payload.update(
            requirements=_requirements(5, "r" * 1_000),
            subject_blocks=[
                {
                    "subject_block_id": "SUBJECT-001",
                    "text": "s" * 4_001,
                    "source_block_id": "block-6",
                }
            ],
        ),
        lambda payload: payload.update(constraints=["bounded"] * 6),
        lambda payload: payload.update(constraints=["c" * 301]),
    ),
)
def test_input_rejects_invalid_identity_or_bounds(mutation) -> None:
    verification = load_requirements_verification()
    payload = deepcopy(valid_input_payload())
    mutation(payload)

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationInput.model_validate(payload)


def test_candidate_accepts_only_bounded_assessment_fields() -> None:
    verification = load_requirements_verification()

    candidate = verification.RequirementsVerificationCandidate(
        assessments=(
            {
                "requirement_id": "REQ-001",
                "status": "partial",
                "evidence": (
                    {
                        "subject_block_id": "SUBJECT-001",
                        "excerpt": "Two sources are included.",
                        "explanation": "This supports the source requirement.",
                    },
                ),
                "gap": "The source authority is not stated.",
                "recommended_action": "Identify each source publisher.",
            },
        ),
        overall_limitations=("Only the supplied text was assessed.",),
    )

    assessment = candidate.assessments[0]
    assert assessment.requirement_id == "REQ-001"
    assert assessment.status == "partial"
    assert assessment.evidence[0].subject_block_id == "SUBJECT-001"
    assert candidate.overall_limitations == (
        "Only the supplied text was assessed.",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(counts={"covered": 1}),
        lambda payload: payload["assessments"][0].update(confidence=0.9),
        lambda payload: payload["assessments"][0]["evidence"][0].update(
            uri="https://example.com"
        ),
        lambda payload: payload["assessments"][0].update(status="unknown"),
        lambda payload: payload["assessments"][0].update(
            evidence=payload["assessments"][0]["evidence"] * 6
        ),
        lambda payload: payload["assessments"][0]["evidence"][0].update(
            excerpt=" "
        ),
        lambda payload: payload["assessments"][0]["evidence"][0].update(
            explanation=" "
        ),
        lambda payload: payload["assessments"][0].update(gap="g" * 1_001),
        lambda payload: payload["assessments"][0].update(
            recommended_action="a" * 1_001
        ),
        lambda payload: payload.update(overall_limitations=["bounded"] * 6),
    ),
)
def test_candidate_schema_rejects_unbounded_or_authoritative_fields(
    mutation,
) -> None:
    verification = load_requirements_verification()
    payload = {
        "assessments": [
            {
                "requirement_id": "REQ-001",
                "status": "partial",
                "evidence": [
                    {
                        "subject_block_id": "SUBJECT-001",
                        "excerpt": "Two sources are included.",
                        "explanation": "This supports the requirement.",
                    }
                ],
                "gap": "Publisher authority is absent.",
                "recommended_action": "Identify each publisher.",
            }
        ],
        "overall_limitations": [],
    }
    mutation(payload)

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationCandidate.model_validate(payload)


def test_strict_models_forbid_extra_fields_and_mutation() -> None:
    verification = load_requirements_verification()
    payload = valid_input_payload()
    payload["server_user_id"] = "must-not-enter-the-expert"

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationInput.model_validate(payload)

    request = verification.RequirementsVerificationInput.model_validate(
        valid_input_payload()
    )
    with pytest.raises(ValidationError):
        request.objective = "Changed after validation."


def five_status_request(verification):
    return verification.RequirementsVerificationInput(
        objective="Assess every requirement against the supplied draft.",
        requirements=tuple(
            {
                "requirement_id": f"REQ-{index:03d}",
                "text": text,
                "source_block_id": f"block-{index}",
            }
            for index, text in enumerate(
                (
                    "Include two sources.",
                    "State every material limitation.",
                    "Provide a CSV export.",
                    "Use only metric measurements.",
                    "Guarantee 99.9 percent uptime.",
                ),
                start=1,
            )
        ),
        subject_blocks=(
            {
                "subject_block_id": "SUBJECT-001",
                "text": "The draft includes two sources from public agencies.",
                "source_block_id": "block-6",
            },
            {
                "subject_block_id": "SUBJECT-002",
                "text": "The draft mentions one limitation but omits duration.",
                "source_block_id": "block-7",
            },
            {
                "subject_block_id": "SUBJECT-003",
                "text": "All measurements are provided in inches.",
                "source_block_id": "block-8",
            },
        ),
    )


def five_status_candidate(verification):
    return verification.RequirementsVerificationCandidate(
        assessments=(
            {
                "requirement_id": "REQ-003",
                "status": "missing",
                "evidence": (),
                "gap": "No CSV export is described.",
                "recommended_action": "Add a CSV export.",
            },
            {
                "requirement_id": "REQ-001",
                "status": "covered",
                "evidence": (
                    {
                        "subject_block_id": "SUBJECT-001",
                        "excerpt": "includes two sources",
                        "explanation": "This directly addresses the requirement.",
                    },
                ),
                "gap": None,
                "recommended_action": None,
            },
            {
                "requirement_id": "REQ-005",
                "status": "unsupported",
                "evidence": (),
                "gap": "No operational evidence establishes uptime.",
                "recommended_action": "Provide measured uptime records.",
            },
            {
                "requirement_id": "REQ-002",
                "status": "partial",
                "evidence": (
                    {
                        "subject_block_id": "SUBJECT-002",
                        "excerpt": "mentions one limitation",
                        "explanation": "Some limitation coverage is present.",
                    },
                ),
                "gap": "The limitation duration is absent.",
                "recommended_action": "State the duration.",
            },
            {
                "requirement_id": "REQ-004",
                "status": "contradictory",
                "evidence": (
                    {
                        "subject_block_id": "SUBJECT-003",
                        "excerpt": "provided in inches",
                        "explanation": "Inches conflict with metric-only output.",
                    },
                ),
                "gap": "The measurement system conflicts.",
                "recommended_action": "Convert measurements to metric units.",
            },
        ),
        overall_limitations=("Only the supplied draft was assessed.",),
    )


def test_valid_candidate_normalizes_order_counts_and_exact_evidence() -> None:
    verification = load_requirements_verification()
    request = five_status_request(verification)
    candidate = five_status_candidate(verification)

    result = verification.normalize_requirements_verification_candidate(
        request,
        candidate,
    )

    assert result.capability is ExpertCapability.REQUIREMENTS_VERIFICATION
    assert result.status is ExpertStatus.COMPLETED
    assert result.summary == (
        "Requirements verification completed for 5 requirements."
    )
    assert result.limitations == ("Only the supplied draft was assessed.",)
    assert result.payload is not None
    assert tuple(
        assessment.requirement_id for assessment in result.payload.assessments
    ) == ("REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005")
    assert result.payload.assessments[0].requirement_text == (
        "Include two sources."
    )
    assert result.payload.assessments[0].evidence[0].excerpt == (
        "includes two sources"
    )
    assert result.payload.counts.model_dump() == {
        "covered": 1,
        "partial": 1,
        "missing": 1,
        "contradictory": 1,
        "unsupported": 1,
    }
    assert result.payload.overall_limitations == (
        "Only the supplied draft was assessed.",
    )
    assert result.evidence is not None
    assert result.evidence.requirement_count == 5
    assert result.evidence.assessed_requirement_count == 5
    assert result.evidence.validated_evidence_count == 3
    assert result.evidence.referenced_subject_block_ids == (
        "SUBJECT-001",
        "SUBJECT-002",
        "SUBJECT-003",
    )


@pytest.mark.parametrize("identity_failure", ("omitted", "duplicate", "unknown"))
def test_identity_failure_rejects_the_candidate_atomically(
    identity_failure: str,
) -> None:
    verification = load_requirements_verification()
    request = five_status_request(verification)
    payload = five_status_candidate(verification).model_dump(mode="json")
    assessments = payload["assessments"]
    if identity_failure == "omitted":
        assessments.pop()
    elif identity_failure == "duplicate":
        assessments.append(deepcopy(assessments[0]))
    else:
        assessments[0]["requirement_id"] = "REQ-006"
    candidate = verification.RequirementsVerificationCandidate.model_validate(
        payload
    )

    result = verification.normalize_requirements_verification_candidate(
        request,
        candidate,
    )

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.summary is None
    assert result.limitations == ()
    assert result.payload is None
    assert result.evidence is None


@pytest.mark.parametrize(
    "evidence_failure",
    (
        "unknown_subject",
        "absent_excerpt",
        "case_changed_excerpt",
        "whitespace_normalized_excerpt",
        "duplicate_evidence",
    ),
)
def test_ungrounded_evidence_rejects_the_candidate_atomically(
    evidence_failure: str,
) -> None:
    verification = load_requirements_verification()
    request = five_status_request(verification)
    payload = five_status_candidate(verification).model_dump(mode="json")
    covered_evidence = payload["assessments"][1]["evidence"]
    if evidence_failure == "unknown_subject":
        covered_evidence[0]["subject_block_id"] = "SUBJECT-004"
    elif evidence_failure == "absent_excerpt":
        covered_evidence[0]["excerpt"] = "includes three sources"
    elif evidence_failure == "case_changed_excerpt":
        covered_evidence[0]["excerpt"] = "Includes two sources"
    elif evidence_failure == "whitespace_normalized_excerpt":
        covered_evidence[0]["excerpt"] = "includes  two sources"
    else:
        covered_evidence.append(deepcopy(covered_evidence[0]))
    candidate = verification.RequirementsVerificationCandidate.model_validate(
        payload
    )

    result = verification.normalize_requirements_verification_candidate(
        request,
        candidate,
    )

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.payload is None
    assert result.evidence is None


@pytest.mark.parametrize(
    "explanation",
    (
        "See https://example.com for proof.",
        "A separate locator block-9 supplies the evidence.",
        "Another assessment REQ-009 proves this.",
        "Unselected SUBJECT-009 contains the details.",
    ),
)
def test_evidence_explanation_cannot_introduce_external_provenance(
    explanation: str,
) -> None:
    verification = load_requirements_verification()
    request = five_status_request(verification)
    payload = five_status_candidate(verification).model_dump(mode="json")
    payload["assessments"][1]["evidence"][0]["explanation"] = explanation
    candidate = verification.RequirementsVerificationCandidate.model_validate(
        payload
    )

    result = verification.normalize_requirements_verification_candidate(
        request,
        candidate,
    )

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.evidence is None


@pytest.mark.parametrize(
    "assessment_index,field,value",
    (
        (1, "evidence", []),
        (1, "gap", "A covered result cannot carry a gap."),
        (1, "recommended_action", "A covered result needs no action."),
        (3, "evidence", []),
        (3, "gap", None),
        (3, "recommended_action", None),
        (
            0,
            "evidence",
            [
                {
                    "subject_block_id": "SUBJECT-001",
                    "excerpt": "includes two sources",
                    "explanation": "This is not evidence of a missing item.",
                }
            ],
        ),
        (0, "gap", None),
        (0, "recommended_action", None),
        (4, "evidence", []),
        (4, "gap", None),
        (4, "recommended_action", None),
        (2, "gap", None),
        (2, "recommended_action", None),
    ),
)
def test_incoherent_status_structure_rejects_the_candidate_atomically(
    assessment_index: int,
    field: str,
    value: object,
) -> None:
    verification = load_requirements_verification()
    request = five_status_request(verification)
    payload = five_status_candidate(verification).model_dump(mode="json")
    payload["assessments"][assessment_index][field] = value
    candidate = verification.RequirementsVerificationCandidate.model_validate(
        payload
    )

    result = verification.normalize_requirements_verification_candidate(
        request,
        candidate,
    )

    assert result.status is ExpertStatus.INVALID_OUTPUT
    assert result.payload is None
    assert result.evidence is None


@pytest.mark.parametrize(
    "inconsistency",
    (
        "status_counts",
        "assessment_order",
        "requirement_count",
        "assessed_requirement_count",
        "evidence_count",
        "referenced_subject_ids",
    ),
)
def test_normalized_result_rejects_internally_inconsistent_derivations(
    inconsistency: str,
) -> None:
    verification = load_requirements_verification()
    result = verification.normalize_requirements_verification_candidate(
        five_status_request(verification),
        five_status_candidate(verification),
    )
    payload = result.model_dump(mode="json")
    if inconsistency == "status_counts":
        payload["payload"]["counts"]["covered"] = 2
    elif inconsistency == "assessment_order":
        payload["payload"]["assessments"][0:2] = reversed(
            payload["payload"]["assessments"][0:2]
        )
    elif inconsistency == "requirement_count":
        payload["evidence"]["requirement_count"] = 4
    elif inconsistency == "assessed_requirement_count":
        payload["evidence"]["assessed_requirement_count"] = 4
    elif inconsistency == "evidence_count":
        payload["evidence"]["validated_evidence_count"] = 2
    else:
        payload["evidence"]["referenced_subject_block_ids"] = [
            "SUBJECT-001"
        ]

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationResult.model_validate(payload)


def test_normalized_assessment_cannot_bypass_status_coherence() -> None:
    verification = load_requirements_verification()
    result = verification.normalize_requirements_verification_candidate(
        five_status_request(verification),
        five_status_candidate(verification),
    )
    payload = result.model_dump(mode="json")
    assessment = payload["payload"]["assessments"][0]
    assessment["status"] = "missing"
    assessment["gap"] = "The requirement is absent."
    assessment["recommended_action"] = "Add the requirement."
    payload["payload"]["counts"]["covered"] = 0
    payload["payload"]["counts"]["missing"] = 2

    with pytest.raises(ValidationError):
        verification.RequirementsVerificationResult.model_validate(payload)


def test_completed_verification_derives_one_action_and_no_citations() -> None:
    verification = load_requirements_verification()
    result = verification.normalize_requirements_verification_candidate(
        five_status_request(verification),
        five_status_candidate(verification),
    )

    receipts = verification.build_requirements_verification_receipts(result)

    assert tuple(action.model_dump() for action in receipts.actions) == (
        {"action_name": "verify_requirements", "status": "completed"},
    )
    assert receipts.citations == ()


@pytest.mark.parametrize(
    "status",
    tuple(
        status
        for status in ExpertStatus
        if status is not ExpertStatus.COMPLETED
    ),
)
def test_noncompleted_verification_derives_no_receipts(
    status: ExpertStatus,
) -> None:
    verification = load_requirements_verification()
    result = verification.RequirementsVerificationResult(status=status)

    receipts = verification.build_requirements_verification_receipts(result)

    assert receipts.actions == ()
    assert receipts.citations == ()
