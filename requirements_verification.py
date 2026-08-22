"""Provider-independent Requirements Verification contracts and validation."""

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agent_col_text_projection import RoutingTextBlockId
from expert_contracts import ExpertCapability, ExpertResult, ExpertStatus
from schemas import AgentActionReceipt, CitationReference


RequirementId = Annotated[
    str,
    StringConstraints(pattern=r"^REQ-(?:00[1-9]|0[1-4][0-9]|050)$"),
]
SubjectBlockId = Annotated[
    str,
    StringConstraints(pattern=r"^SUBJECT-(?:00[1-9]|0[12][0-9]|03[0-2])$"),
]
VerificationObjective = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
RequirementText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1_000),
]
SubjectBlockText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=8_000),
]
VerificationConstraint = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
EvidenceExcerpt = Annotated[
    str,
    StringConstraints(min_length=1, max_length=500),
]
EvidenceExplanation = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
AssessmentText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
VerificationLimitation = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
_EXTERNAL_PROVENANCE_PATTERN = re.compile(
    r"(?:https?://|www\.|\bblock-\d+\b|\bREQ-\d+\b|\bSUBJECT-\d+\b)",
    re.IGNORECASE,
)


class StrictRequirementsVerificationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class RequirementInput(StrictRequirementsVerificationModel):
    requirement_id: RequirementId
    text: RequirementText
    source_block_id: RoutingTextBlockId

    @field_validator("text")
    @classmethod
    def reject_whitespace_only_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Requirement text cannot be whitespace only.")
        return value


class SubjectBlock(StrictRequirementsVerificationModel):
    subject_block_id: SubjectBlockId
    text: SubjectBlockText
    source_block_id: RoutingTextBlockId

    @field_validator("text")
    @classmethod
    def reject_whitespace_only_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Subject text cannot be whitespace only.")
        return value


class RequirementsVerificationInput(StrictRequirementsVerificationModel):
    objective: VerificationObjective
    requirements: tuple[RequirementInput, ...] = Field(
        min_length=1,
        max_length=50,
    )
    subject_blocks: tuple[SubjectBlock, ...] = Field(
        min_length=1,
        max_length=32,
    )
    constraints: tuple[VerificationConstraint, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_local_identity_and_bounds(self) -> Self:
        expected_requirement_ids = tuple(
            f"REQ-{index:03d}"
            for index in range(1, len(self.requirements) + 1)
        )
        actual_requirement_ids = tuple(
            requirement.requirement_id for requirement in self.requirements
        )
        if actual_requirement_ids != expected_requirement_ids:
            raise ValueError("Requirement IDs must be sequential.")

        expected_subject_ids = tuple(
            f"SUBJECT-{index:03d}"
            for index in range(1, len(self.subject_blocks) + 1)
        )
        actual_subject_ids = tuple(
            subject.subject_block_id for subject in self.subject_blocks
        )
        if actual_subject_ids != expected_subject_ids:
            raise ValueError("Subject block IDs must be sequential.")

        requirement_source_ids = tuple(
            requirement.source_block_id for requirement in self.requirements
        )
        subject_source_ids = tuple(
            subject.source_block_id for subject in self.subject_blocks
        )
        all_source_ids = requirement_source_ids + subject_source_ids
        if len(set(all_source_ids)) != len(all_source_ids):
            raise ValueError("Requirement and subject source blocks must be unique.")
        requirement_source_indexes = tuple(
            int(source_id.removeprefix("block-"))
            for source_id in requirement_source_ids
        )
        subject_source_indexes = tuple(
            int(source_id.removeprefix("block-"))
            for source_id in subject_source_ids
        )
        if requirement_source_indexes != tuple(
            sorted(requirement_source_indexes)
        ):
            raise ValueError("Requirement source blocks must remain ordered.")
        if subject_source_indexes != tuple(sorted(subject_source_indexes)):
            raise ValueError("Subject source blocks must remain ordered.")

        requirement_characters = sum(
            len(requirement.text) for requirement in self.requirements
        )
        subject_characters = sum(
            len(subject.text) for subject in self.subject_blocks
        )
        if requirement_characters > 6_000:
            raise ValueError("Requirement text exceeds the aggregate limit.")
        if subject_characters > 8_000:
            raise ValueError("Subject text exceeds the aggregate limit.")
        if requirement_characters + subject_characters > 9_000:
            raise ValueError("Combined verification text exceeds the limit.")
        return self


class RequirementAssessmentStatus(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    MISSING = "missing"
    CONTRADICTORY = "contradictory"
    UNSUPPORTED = "unsupported"


class SubjectEvidenceCandidate(StrictRequirementsVerificationModel):
    subject_block_id: SubjectBlockId
    excerpt: EvidenceExcerpt
    explanation: EvidenceExplanation

    @field_validator("excerpt")
    @classmethod
    def reject_whitespace_only_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence excerpt cannot be whitespace only.")
        return value


class RequirementAssessmentCandidate(StrictRequirementsVerificationModel):
    requirement_id: RequirementId
    status: RequirementAssessmentStatus
    evidence: tuple[SubjectEvidenceCandidate, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    gap: AssessmentText | None = None
    recommended_action: AssessmentText | None = None


class RequirementsVerificationCandidate(StrictRequirementsVerificationModel):
    assessments: tuple[RequirementAssessmentCandidate, ...] = Field(
        min_length=1,
        max_length=50,
    )
    overall_limitations: tuple[VerificationLimitation, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )


class SubjectEvidence(StrictRequirementsVerificationModel):
    subject_block_id: SubjectBlockId
    excerpt: EvidenceExcerpt
    explanation: EvidenceExplanation


class RequirementAssessment(StrictRequirementsVerificationModel):
    requirement_id: RequirementId
    requirement_text: RequirementText
    status: RequirementAssessmentStatus
    evidence: tuple[SubjectEvidence, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    gap: AssessmentText | None = None
    recommended_action: AssessmentText | None = None

    @model_validator(mode="after")
    def require_coherent_status_structure(self) -> Self:
        if not _has_coherent_status_structure(self):
            raise ValueError("Normalized assessment status is incoherent.")
        return self


class RequirementStatusCounts(StrictRequirementsVerificationModel):
    covered: int = Field(ge=0, le=50)
    partial: int = Field(ge=0, le=50)
    missing: int = Field(ge=0, le=50)
    contradictory: int = Field(ge=0, le=50)
    unsupported: int = Field(ge=0, le=50)


class RequirementsVerificationPayload(StrictRequirementsVerificationModel):
    assessments: tuple[RequirementAssessment, ...] = Field(
        min_length=1,
        max_length=50,
    )
    counts: RequirementStatusCounts
    overall_limitations: tuple[VerificationLimitation, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_local_order_and_counts(self) -> Self:
        expected_ids = tuple(
            f"REQ-{index:03d}"
            for index in range(1, len(self.assessments) + 1)
        )
        actual_ids = tuple(
            assessment.requirement_id for assessment in self.assessments
        )
        if actual_ids != expected_ids:
            raise ValueError("Normalized assessments must remain ordered.")
        for status in RequirementAssessmentStatus:
            actual_count = sum(
                assessment.status is status
                for assessment in self.assessments
            )
            if getattr(self.counts, status.value) != actual_count:
                raise ValueError("Status counts must match assessments.")
        return self


class RequirementsVerificationEvidence(StrictRequirementsVerificationModel):
    requirement_count: int = Field(ge=1, le=50)
    assessed_requirement_count: int = Field(ge=1, le=50)
    validated_evidence_count: int = Field(ge=0, le=250)
    referenced_subject_block_ids: tuple[SubjectBlockId, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )


class RequirementsVerificationResult(
    ExpertResult[
        RequirementsVerificationPayload,
        RequirementsVerificationEvidence,
    ]
):
    capability: Literal[ExpertCapability.REQUIREMENTS_VERIFICATION] = (
        ExpertCapability.REQUIREMENTS_VERIFICATION
    )

    @model_validator(mode="after")
    def require_completed_derivations(self) -> Self:
        if self.status is not ExpertStatus.COMPLETED:
            return self
        assert self.payload is not None
        assert self.evidence is not None
        assessment_count = len(self.payload.assessments)
        validated_evidence_count = sum(
            len(assessment.evidence)
            for assessment in self.payload.assessments
        )
        referenced_subject_ids = {
            evidence.subject_block_id
            for assessment in self.payload.assessments
            for evidence in assessment.evidence
        }
        reported_subject_ids = self.evidence.referenced_subject_block_ids
        if (
            self.evidence.requirement_count != assessment_count
            or self.evidence.assessed_requirement_count != assessment_count
            or self.evidence.validated_evidence_count
            != validated_evidence_count
            or len(reported_subject_ids) != len(set(reported_subject_ids))
            or set(reported_subject_ids) != referenced_subject_ids
        ):
            raise ValueError(
                "Requirements verification evidence must match its payload."
            )
        return self


@dataclass(frozen=True, slots=True)
class RequirementsVerificationReceipts:
    actions: tuple[AgentActionReceipt, ...] = ()
    citations: tuple[CitationReference, ...] = ()


def build_requirements_verification_receipts(
    result: RequirementsVerificationResult,
) -> RequirementsVerificationReceipts:
    """Return one action only for completed local verification."""
    if result.status is not ExpertStatus.COMPLETED:
        return RequirementsVerificationReceipts()
    return RequirementsVerificationReceipts(
        actions=(
            AgentActionReceipt(
                action_name="verify_requirements",
                status="completed",
            ),
        ),
    )


def _invalid_requirements_verification_result() -> RequirementsVerificationResult:
    return RequirementsVerificationResult(status=ExpertStatus.INVALID_OUTPUT)


def _has_coherent_status_structure(
    assessment: RequirementAssessmentCandidate | RequirementAssessment,
) -> bool:
    has_evidence = bool(assessment.evidence)
    has_gap = assessment.gap is not None
    has_action = assessment.recommended_action is not None
    if assessment.status is RequirementAssessmentStatus.COVERED:
        return has_evidence and not has_gap and not has_action
    if assessment.status is RequirementAssessmentStatus.PARTIAL:
        return has_evidence and has_gap and has_action
    if assessment.status is RequirementAssessmentStatus.MISSING:
        return not has_evidence and has_gap and has_action
    if assessment.status is RequirementAssessmentStatus.CONTRADICTORY:
        return has_evidence and has_gap and has_action
    return has_gap and has_action


def normalize_requirements_verification_candidate(
    request: RequirementsVerificationInput,
    candidate: RequirementsVerificationCandidate,
) -> RequirementsVerificationResult:
    """Normalize one provider candidate into local requirement order."""
    expected_requirement_ids = tuple(
        requirement.requirement_id for requirement in request.requirements
    )
    candidate_requirement_ids = tuple(
        assessment.requirement_id for assessment in candidate.assessments
    )
    if (
        len(candidate_requirement_ids) != len(set(candidate_requirement_ids))
        or len(candidate_requirement_ids) != len(expected_requirement_ids)
        or set(candidate_requirement_ids) != set(expected_requirement_ids)
    ):
        return _invalid_requirements_verification_result()

    subjects_by_id = {
        subject.subject_block_id: subject for subject in request.subject_blocks
    }
    for assessment in candidate.assessments:
        if not _has_coherent_status_structure(assessment):
            return _invalid_requirements_verification_result()
        evidence_keys: set[tuple[str, str]] = set()
        for evidence in assessment.evidence:
            subject = subjects_by_id.get(evidence.subject_block_id)
            evidence_key = (evidence.subject_block_id, evidence.excerpt)
            if (
                subject is None
                or evidence.excerpt not in subject.text
                or evidence_key in evidence_keys
                or _EXTERNAL_PROVENANCE_PATTERN.search(evidence.explanation)
            ):
                return _invalid_requirements_verification_result()
            evidence_keys.add(evidence_key)

    candidates_by_id = {
        assessment.requirement_id: assessment
        for assessment in candidate.assessments
    }
    normalized_assessments: list[RequirementAssessment] = []
    status_counts = {
        status.value: 0 for status in RequirementAssessmentStatus
    }
    referenced_subject_ids: set[str] = set()
    evidence_count = 0

    for requirement in request.requirements:
        assessment = candidates_by_id[requirement.requirement_id]
        normalized_evidence = tuple(
            SubjectEvidence(
                subject_block_id=evidence.subject_block_id,
                excerpt=evidence.excerpt,
                explanation=evidence.explanation,
            )
            for evidence in assessment.evidence
        )
        normalized_assessments.append(
            RequirementAssessment(
                requirement_id=requirement.requirement_id,
                requirement_text=requirement.text,
                status=assessment.status,
                evidence=normalized_evidence,
                gap=assessment.gap,
                recommended_action=assessment.recommended_action,
            )
        )
        status_counts[assessment.status.value] += 1
        evidence_count += len(normalized_evidence)
        referenced_subject_ids.update(
            evidence.subject_block_id for evidence in normalized_evidence
        )

    referenced_subject_block_ids = tuple(
        subject.subject_block_id
        for subject in request.subject_blocks
        if subject.subject_block_id in referenced_subject_ids
    )
    requirement_count = len(request.requirements)
    return RequirementsVerificationResult(
        status=ExpertStatus.COMPLETED,
        summary=(
            "Requirements verification completed for "
            f"{requirement_count} requirements."
        ),
        limitations=candidate.overall_limitations,
        payload=RequirementsVerificationPayload(
            assessments=tuple(normalized_assessments),
            counts=RequirementStatusCounts(**status_counts),
            overall_limitations=candidate.overall_limitations,
        ),
        evidence=RequirementsVerificationEvidence(
            requirement_count=requirement_count,
            assessed_requirement_count=len(normalized_assessments),
            validated_evidence_count=evidence_count,
            referenced_subject_block_ids=referenced_subject_block_ids,
        ),
    )
