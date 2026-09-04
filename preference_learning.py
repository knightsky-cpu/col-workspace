import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from memory_policy import MemoryCategoryV2, validate_memory_value_for_policy
from schemas import IdentifierStr, StrictModel


PreferenceObservationAuthority = Literal["non_authoritative_observation"]
PreferenceHypothesisAuthority = Literal["non_authoritative_hypothesis"]
EvidenceKind = Literal[
    "user_correction",
    "explicit_feedback_pattern",
    "repeated_collaboration_preference",
]
PreferenceEvidenceSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
HYPOTHESIS_SURFACE_MIN_CONFIDENCE = 0.70
HYPOTHESIS_SURFACE_MIN_EVIDENCE = 2
HYPOTHESIS_MAX_AGE = timedelta(days=30)


class PreferenceObservation(StrictModel):
    observation_id: IdentifierStr
    authority: PreferenceObservationAuthority = "non_authoritative_observation"
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    source_turn_id: IdentifierStr
    source_message_id: IdentifierStr
    category: MemoryCategoryV2
    canonical_value: object
    evidence_kind: EvidenceKind
    evidence_summary: PreferenceEvidenceSummary
    confidence_delta: float = Field(ge=0.0, le=0.5)
    created_at: datetime
    is_active_memory: Literal[False] = False
    can_adapt_response: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy_value(self) -> "PreferenceObservation":
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


class PreferenceHypothesis(StrictModel):
    hypothesis_id: IdentifierStr
    authority: PreferenceHypothesisAuthority = "non_authoritative_hypothesis"
    user_id: IdentifierStr
    project_id: IdentifierStr
    category: MemoryCategoryV2
    canonical_value: object
    evidence_count: int = Field(ge=1, le=20)
    contradiction_count: int = Field(ge=0, le=20)
    confidence: float = Field(ge=0.0, le=1.0)
    source_observation_ids: tuple[IdentifierStr, ...] = Field(max_length=20)
    first_observed_at: datetime
    last_observed_at: datetime
    is_active_memory: Literal[False] = False
    can_adapt_response: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy_value(self) -> "PreferenceHypothesis":
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


class PreferenceLearningCaptureOutcome(StrictModel):
    observation: PreferenceObservation
    hypothesis: PreferenceHypothesis
    surfaced_hypothesis: PreferenceHypothesis | None = None

    @model_validator(mode="after")
    def validate_surface_snapshot(self) -> "PreferenceLearningCaptureOutcome":
        if (
            self.surfaced_hypothesis is not None
            and self.surfaced_hypothesis != self.hypothesis
        ):
            raise ValueError(
                "Surfaced preference hypothesis must match the capture outcome."
            )
        return self


def preference_hypothesis_confirmation_digest(
    *,
    user_id: str,
    project_id: str,
    session_id: str,
    source_message_id: str,
    hypothesis: PreferenceHypothesis,
) -> str:
    """Derive retry-safe identity for one accepted preference hypothesis."""
    material = json.dumps(
        {
            "namespace": "agent-col-preference-confirmation-v1",
            "user_id": user_id,
            "project_id": project_id,
            "session_id": session_id,
            "source_message_id": source_message_id,
            "hypothesis": hypothesis.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def validate_preference_observation(value: object) -> PreferenceObservation:
    return PreferenceObservation.model_validate(value)


def derive_preference_hypothesis_id(observation: PreferenceObservation) -> str:
    return (
        f"pref-hyp--{observation.user_id}--{observation.project_id}--"
        f"{observation.category}"
    )


def merge_observation_into_hypothesis(
    existing: PreferenceHypothesis | None,
    observation: PreferenceObservation | object,
    *,
    now: datetime,
) -> PreferenceHypothesis | None:
    validated = validate_preference_observation(observation)
    if existing is not None and (
        validated.observation_id in existing.source_observation_ids
    ):
        return existing
    if existing is None:
        return PreferenceHypothesis(
            hypothesis_id=derive_preference_hypothesis_id(validated),
            user_id=validated.user_id,
            project_id=validated.project_id,
            category=validated.category,
            canonical_value=validated.canonical_value,
            evidence_count=1,
            contradiction_count=0,
            confidence=min(validated.confidence_delta, 1.0),
            source_observation_ids=(validated.observation_id,),
            first_observed_at=validated.created_at,
            last_observed_at=now,
        )
    if (
        existing.user_id != validated.user_id
        or existing.project_id != validated.project_id
        or existing.category != validated.category
    ):
        raise ValueError("Observation does not match hypothesis scope.")
    if existing.canonical_value != validated.canonical_value:
        return existing.model_copy(
            update={
                "contradiction_count": existing.contradiction_count + 1,
                "confidence": max(
                    existing.confidence - validated.confidence_delta,
                    0.0,
                ),
                "source_observation_ids": (
                    *existing.source_observation_ids,
                    validated.observation_id,
                ),
                "last_observed_at": now,
            }
        )
    return existing.model_copy(
        update={
            "evidence_count": existing.evidence_count + 1,
            "confidence": min(
                existing.confidence + validated.confidence_delta,
                1.0,
            ),
            "source_observation_ids": (
                *existing.source_observation_ids,
                validated.observation_id,
            ),
            "last_observed_at": now,
        }
    )


def should_surface_hypothesis(
    hypothesis: PreferenceHypothesis,
    *,
    now: datetime,
) -> bool:
    return (
        hypothesis.evidence_count >= HYPOTHESIS_SURFACE_MIN_EVIDENCE
        and hypothesis.confidence >= HYPOTHESIS_SURFACE_MIN_CONFIDENCE
        and hypothesis.contradiction_count == 0
        and now - hypothesis.last_observed_at <= HYPOTHESIS_MAX_AGE
    )
