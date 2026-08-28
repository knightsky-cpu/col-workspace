import _repo_path
"""Run the offline Requirements Verification validator acceptance check."""

from collections.abc import Callable

from expert_contracts import ExpertStatus
from requirements_verification import (
    RequirementsVerificationCandidate,
    RequirementsVerificationInput,
    RequirementsVerificationResult,
    normalize_requirements_verification_candidate,
)


DEFAULT_REQUEST = RequirementsVerificationInput(
    objective="Assess every requirement against the supplied subject.",
    requirements=(
        {
            "requirement_id": "REQ-001",
            "text": "Include two sources.",
            "source_block_id": "block-1",
        },
        {
            "requirement_id": "REQ-002",
            "text": "State every material limitation.",
            "source_block_id": "block-2",
        },
        {
            "requirement_id": "REQ-003",
            "text": "Provide a CSV export.",
            "source_block_id": "block-3",
        },
        {
            "requirement_id": "REQ-004",
            "text": "Use only metric measurements.",
            "source_block_id": "block-4",
        },
        {
            "requirement_id": "REQ-005",
            "text": "Guarantee 99.9 percent uptime.",
            "source_block_id": "block-5",
        },
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

DEFAULT_CANDIDATE = RequirementsVerificationCandidate(
    assessments=(
        {
            "requirement_id": "REQ-003",
            "status": "missing",
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
        },
        {
            "requirement_id": "REQ-005",
            "status": "unsupported",
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
    overall_limitations=("Only supplied material was assessed.",),
)

Normalizer = Callable[
    [RequirementsVerificationInput, RequirementsVerificationCandidate],
    RequirementsVerificationResult,
]


def run_smoke(
    *,
    normalizer: Normalizer = normalize_requirements_verification_candidate,
    output: Callable[[str], object] = print,
) -> int:
    """Return zero only when valid and invalid local paths are both proven."""
    completed = normalizer(DEFAULT_REQUEST, DEFAULT_CANDIDATE)
    invalid_payload = DEFAULT_CANDIDATE.model_dump(mode="json")
    invalid_payload["assessments"][1]["evidence"][0]["excerpt"] = (
        "not present in the subject"
    )
    invalid_candidate = RequirementsVerificationCandidate.model_validate(
        invalid_payload
    )
    invalid = normalizer(DEFAULT_REQUEST, invalid_candidate)

    expected_counts = {
        "covered": 1,
        "partial": 1,
        "missing": 1,
        "contradictory": 1,
        "unsupported": 1,
    }
    completed_is_valid = (
        completed.status is ExpertStatus.COMPLETED
        and completed.payload is not None
        and completed.evidence is not None
        and completed.payload.counts.model_dump() == expected_counts
        and completed.evidence.requirement_count == 5
        and completed.evidence.assessed_requirement_count == 5
        and completed.evidence.validated_evidence_count == 3
    )
    invalid_is_atomic = (
        invalid.status is ExpertStatus.INVALID_OUTPUT
        and invalid.summary is None
        and invalid.limitations == ()
        and invalid.payload is None
        and invalid.evidence is None
    )
    if not completed_is_valid or not invalid_is_atomic:
        output("requirements-verification-validator failed")
        return 1

    output(
        "requirements-verification-validator pass "
        "requirements=5 assessed=5 evidence=3 all_statuses=true "
        "ungrounded_rejected=true"
    )
    return 0


def main() -> None:
    raise SystemExit(run_smoke())


if __name__ == "__main__":
    main()
