import json
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from memory_policy import (
    AccessibilitySupport,
    BroadRole,
    DevelopmentEnvironment,
    ExplanationPace,
    IdentityContextPolicy,
    LearningApproach,
    MemoryCategoryV2,
    PreferredNameStr,
    UserRequestedMemoryStr,
    validate_memory_value_for_policy,
)
from schemas import DomainExperienceEntry, StrictModel


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


class _ProviderCandidateBase(StrictModel):
    kind: Literal["profile_candidate"] = "profile_candidate"
    evidence_text: str = Field(min_length=1, max_length=500)


class ResponseLengthProviderCandidate(_ProviderCandidateBase):
    category: Literal["response_length"]
    canonical_value: Literal["concise", "balanced", "detailed"]


class ExplanationStructureProviderCandidate(_ProviderCandidateBase):
    category: Literal["explanation_structure"]
    canonical_value: Literal[
        "direct_then_steps",
        "step_by_step",
        "concept_then_example",
    ]


class ExampleUsageProviderCandidate(_ProviderCandidateBase):
    category: Literal["example_usage"]
    canonical_value: Literal["none", "when_helpful", "always_practical"]


class QuestionStyleProviderCandidate(_ProviderCandidateBase):
    category: Literal["question_style"]
    canonical_value: Literal[
        "ask_before_assuming",
        "recommend_then_ask",
        "minimal_follow_up",
    ]


class PlanningGranularityProviderCandidate(_ProviderCandidateBase):
    category: Literal["planning_granularity"]
    canonical_value: Literal["milestones", "tasks", "micro_steps"]


class ProgressCheckInsProviderCandidate(_ProviderCandidateBase):
    category: Literal["progress_check_ins"]
    canonical_value: Literal[
        "only_when_blocked",
        "at_milestones",
        "frequent",
    ]


class ToolUseStyleProviderCandidate(_ProviderCandidateBase):
    category: Literal["tool_use_style"]
    canonical_value: Literal[
        "ask_before_external_tools",
        "use_when_needed",
        "minimize_tools",
    ]


class FormattingStyleProviderCandidate(_ProviderCandidateBase):
    category: Literal["formatting_style"]
    canonical_value: Literal["prose", "bullets", "mixed"]


class PreferredNameProviderCandidate(_ProviderCandidateBase):
    category: Literal["preferred_name"]
    canonical_value: PreferredNameStr


class BroadRolesProviderCandidate(_ProviderCandidateBase):
    category: Literal["broad_roles"]
    canonical_value: list[BroadRole] = Field(min_length=1, max_length=3)


class ExplanationPaceProviderCandidate(_ProviderCandidateBase):
    category: Literal["explanation_pace"]
    canonical_value: ExplanationPace


class LearningApproachProviderCandidate(_ProviderCandidateBase):
    category: Literal["learning_approach"]
    canonical_value: LearningApproach


class AccessibilitySupportProviderCandidate(_ProviderCandidateBase):
    category: Literal["accessibility_support"]
    canonical_value: list[AccessibilitySupport] = Field(
        min_length=1,
        max_length=3,
    )


class DevelopmentEnvironmentsProviderCandidate(_ProviderCandidateBase):
    category: Literal["development_environments"]
    canonical_value: list[DevelopmentEnvironment] = Field(
        min_length=1,
        max_length=3,
    )


class DomainExperienceProviderCandidate(_ProviderCandidateBase):
    category: Literal["domain_experience"]
    canonical_value: list[DomainExperienceEntry] = Field(
        min_length=1,
        max_length=3,
    )


class UserRequestedMemoryProviderCandidate(_ProviderCandidateBase):
    category: Literal["user_requested_memory"]
    canonical_value: UserRequestedMemoryStr


ProviderProfileCandidate = Annotated[
    ResponseLengthProviderCandidate
    | ExplanationStructureProviderCandidate
    | ExampleUsageProviderCandidate
    | QuestionStyleProviderCandidate
    | PlanningGranularityProviderCandidate
    | ProgressCheckInsProviderCandidate
    | ToolUseStyleProviderCandidate
    | FormattingStyleProviderCandidate
    | PreferredNameProviderCandidate
    | BroadRolesProviderCandidate
    | ExplanationPaceProviderCandidate
    | LearningApproachProviderCandidate
    | AccessibilitySupportProviderCandidate
    | DevelopmentEnvironmentsProviderCandidate
    | DomainExperienceProviderCandidate
    | UserRequestedMemoryProviderCandidate,
    Field(discriminator="category"),
]


class ProviderClarifyDecision(StrictModel):
    kind: Literal["clarify"] = "clarify"
    candidates: list[ProviderProfileCandidate] = Field(
        min_length=2,
        max_length=5,
    )


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

ProviderNaturalMemoryDecision = (
    NoMemoryDecision
    | SessionOnlyDecision
    | WorkspaceNoteDecision
    | ProviderProfileCandidate
    | ProviderClarifyDecision
    | UnsupportedDecision
    | ProhibitedDecision
)

_PROVIDER_DECISION_ADAPTER = TypeAdapter(ProviderNaturalMemoryDecision)
_NATURAL_DECISION_ADAPTER = TypeAdapter(NaturalMemoryDecision)
_NATURAL_DECISION_TYPES = (
    NoMemoryDecision,
    SessionOnlyDecision,
    WorkspaceNoteDecision,
    ProfileCandidateDecision,
    ClarifyDecision,
    UnsupportedDecision,
    ProhibitedDecision,
)


def validate_provider_natural_memory_decision(
    value: object,
) -> NaturalMemoryDecision:
    """Convert one untrusted provider decision to its canonical model."""
    provider_decision = _PROVIDER_DECISION_ADAPTER.validate_python(value)
    return _NATURAL_DECISION_ADAPTER.validate_python(
        provider_decision.model_dump(mode="python")
    )


def is_natural_memory_decision(value: object) -> bool:
    """Return whether a value is already one canonical decision model."""
    return isinstance(value, _NATURAL_DECISION_TYPES)


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
