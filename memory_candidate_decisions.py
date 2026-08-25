import json
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from memory_policy import (
    IdentityContextPolicy,
    MemoryCategoryV2,
    validate_memory_value_for_policy,
)
from schemas import StrictModel


SessionMemoryScope = Literal["current_turn", "active_chat"]
UnsupportedMemoryReason = Literal[
    "unsupported_category",
    "unsupported_value",
    "unsupported_duration",
]
ProhibitedMemoryReason = Literal[
    "credential_or_secret",
    "account_identifier",
    "contact_detail",
    "precise_location",
    "exact_employer_or_school",
    "health_or_financial_fact",
    "protected_trait",
    "identity_provider_claim",
    "inferred_private_trait",
]


class NoMemoryDecision(StrictModel):
    kind: Literal["no_memory"] = "no_memory"


class SessionOnlyDecision(StrictModel):
    kind: Literal["session_only"] = "session_only"
    scope: SessionMemoryScope


class WorkspaceNoteDecision(StrictModel):
    kind: Literal["workspace_note"] = "workspace_note"


class ProfileCandidateDecision(StrictModel):
    kind: Literal["profile_candidate"] = "profile_candidate"
    category: MemoryCategoryV2
    canonical_value: object
    evidence_text: str = Field(min_length=1, max_length=500)

    @field_validator("evidence_text")
    @classmethod
    def require_unicode_scalar_evidence(cls, value: str) -> str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("Evidence text must contain Unicode scalars.")
        return value

    @model_validator(mode="after")
    def validate_canonical_value(self) -> Self:
        normalized = validate_memory_value_for_policy(
            "2.0",
            self.category,
            self.canonical_value,
        )
        object.__setattr__(self, "canonical_value", normalized)
        return self


class ClarifyDecision(StrictModel):
    kind: Literal["clarify"] = "clarify"
    candidates: list[ProfileCandidateDecision] = Field(
        min_length=2,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_unique_candidates(self) -> Self:
        identities = [
            (
                candidate.category,
                json.dumps(
                    candidate.canonical_value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            for candidate in self.candidates
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Clarification candidates must be unique.")
        return self


class UnsupportedDecision(StrictModel):
    kind: Literal["unsupported"] = "unsupported"
    reason_code: UnsupportedMemoryReason


class ProhibitedDecision(StrictModel):
    kind: Literal["prohibited"] = "prohibited"
    reason_code: ProhibitedMemoryReason


NaturalMemoryDecision = Annotated[
    NoMemoryDecision
    | SessionOnlyDecision
    | WorkspaceNoteDecision
    | ProfileCandidateDecision
    | ClarifyDecision
    | UnsupportedDecision
    | ProhibitedDecision,
    Field(discriminator="kind"),
]


def validate_decision_evidence(
    decision: NaturalMemoryDecision,
    source_message: str,
) -> None:
    if type(source_message) is not str:
        raise ValueError("Source message must be a string.")
    if isinstance(decision, ProfileCandidateDecision):
        candidates = (decision,)
    elif isinstance(decision, ClarifyDecision):
        candidates = tuple(decision.candidates)
    else:
        return
    for candidate in candidates:
        if candidate.evidence_text not in source_message:
            raise ValueError(
                "Memory evidence must be an exact substring of the source "
                "message."
            )
        if candidate.category == "preferred_name":
            IdentityContextPolicy.validate(
                "preferred_name",
                candidate.canonical_value,
                current_message=candidate.evidence_text,
                require_grounding=True,
            )
