from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from memory_policy import (
    ConfirmationChannel,
    MEMORY_POLICY_VERSION,
    MEMORY_SCHEMA_VERSION,
    IdentityContextCategory,
    MemoryCategory,
    MemoryDecision,
    MemoryEventType,
    MemoryValue,
    PreferenceCategory,
    validate_memory_value,
)


SYNTHESIS_BLUEPRINT_SCHEMA_VERSION = "2.0"


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
IdentifierStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
SourceText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=10_000,
    ),
]
DisplayLabelStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
ProjectDisplayNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
GeneratedLabelStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
GeneratedTextStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]
VerificationStepStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentActionReceipt(StrictModel):
    action_name: Literal[
        "synthesize_project",
        "google_search",
        "url_context",
        "record_blueprint_feedback",
        "approve_memory_signal",
        "reject_memory_signal",
        "revoke_memory_signal",
        "delete_memory_signal",
    ]
    status: Literal["completed"]


class ArtifactReference(StrictModel):
    artifact_type: Literal["synthesis_blueprint"]
    project_id: IdentifierStr
    artifact_id: IdentifierStr
    schema_version: Literal["2.0"]
    display_label: DisplayLabelStr


class CitationReference(StrictModel):
    uri: HttpUrl
    label: DisplayLabelStr


class ChatRequest(StrictModel):
    project_id: IdentifierStr
    session_id: IdentifierStr
    user_id: IdentifierStr
    message: NonEmptyStr


class ChatResponse(StrictModel):
    response: NonEmptyStr
    actions: list[AgentActionReceipt] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    citations: list[CitationReference] = Field(default_factory=list)


def _normalize_memory_model_value(
    data: object,
    value_field: str,
) -> object:
    if not isinstance(data, Mapping):
        return data
    if "category" not in data or value_field not in data:
        return data
    normalized = dict(data)
    normalized[value_field] = validate_memory_value(
        data["category"],
        data[value_field],
    )
    return normalized


class MemoryProposal(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategory
    proposed_value: MemoryValue
    expected_signal_id: IdentifierStr | None
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    status: Literal["pending", "approved", "rejected"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "proposed_value")


class ActiveMemorySignal(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    source_event_id: IdentifierStr
    approved_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")


class CollaborationProfile(StrictModel):
    memory_schema_version: Literal["1.0"] = MEMORY_SCHEMA_VERSION
    memory_revision: int = Field(default=0, ge=0)
    identity_context: dict[
        IdentityContextCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=2)
    active_preferences: dict[
        PreferenceCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def validate_projection_keys(self) -> Self:
        for key, signal in self.identity_context.items():
            if key != signal.category:
                raise ValueError(
                    "Identity-context key must match signal category."
                )
        for key, signal in self.active_preferences.items():
            if key != signal.category:
                raise ValueError(
                    "Preference key must match signal category."
                )
        return self


class MemoryEvent(StrictModel):
    event_id: IdentifierStr
    event_type: MemoryEventType
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    policy_version: Literal["1.0"] = MEMORY_POLICY_VERSION
    source_type: Literal["explicit_user_feedback"]
    source_session_id: IdentifierStr
    source_message_id: IdentifierStr
    confirmation_channel: ConfirmationChannel
    confirmation_session_id: IdentifierStr | None
    confirmation_message_id: IdentifierStr | None
    related_signal_id: IdentifierStr | None
    memory_revision: int = Field(ge=1)
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")

    @model_validator(mode="after")
    def validate_confirmation_channel(self) -> Self:
        if self.confirmation_channel == "chat_decision":
            valid = (
                self.confirmation_session_id is not None
                and self.confirmation_message_id is not None
            )
        else:
            valid = (
                self.confirmation_session_id is None
                and self.confirmation_message_id is None
            )
        if not valid:
            raise ValueError(
                "Confirmation identifiers do not match the channel."
            )
        return self


class MemoryDecisionRequest(StrictModel):
    proposal_id: IdentifierStr
    decision: MemoryDecision


class MemoryProposalReceipt(StrictModel):
    proposal_id: IdentifierStr
    category: MemoryCategory
    proposed_value: MemoryValue
    expires_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_proposed_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "proposed_value")


class AdaptationReceipt(StrictModel):
    signal_id: IdentifierStr
    category: MemoryCategory
    value: MemoryValue
    source_event_id: IdentifierStr
    status: Literal["provided_to_model"]

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: object) -> object:
        return _normalize_memory_model_value(data, "value")


class MemoryInspectionResponse(StrictModel):
    profile: CollaborationProfile
    unresolved_proposals: list[MemoryProposal] = Field(max_length=10)
    events: list[MemoryEvent] = Field(max_length=50)
    next_event_id: IdentifierStr | None


class MemoryMutationResponse(StrictModel):
    action: AgentActionReceipt
    profile: CollaborationProfile


class ConceptualModel(StrictModel):
    project_name: ProjectDisplayNameStr = Field(
        description="A concise, human-readable project name."
    )
    core_value_proposition: GeneratedTextStr = Field(
        description=(
            "The primary user friction the project solves and the value it "
            "delivers."
        )
    )
    in_scope: list[GeneratedTextStr] = Field(
        min_length=1,
        max_length=10,
        description="Concrete capabilities included in this blueprint.",
    )
    out_of_scope: list[GeneratedTextStr] = Field(
        default_factory=list,
        max_length=10,
        description="Explicitly excluded capabilities or responsibilities.",
    )
    assumptions: list[GeneratedTextStr] = Field(
        default_factory=list,
        max_length=10,
        description="Material assumptions on which the blueprint depends.",
    )


class PersonalizationAdaptation(StrictModel):
    profile_key: GeneratedLabelStr = Field(
        description="The exact non-sensitive user-profile key used."
    )
    architecture_change: GeneratedTextStr = Field(
        description="The specific design change caused by the profile signal."
    )
    reason: GeneratedTextStr = Field(
        description="Why the profile signal justifies that design change."
    )


class PersonalizationTrace(StrictModel):
    adaptations: list[PersonalizationAdaptation] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Profile-grounded adaptations; empty when no profile signal was "
            "used."
        ),
    )


class ArchitecturalAlternative(StrictModel):
    option_name: GeneratedLabelStr = Field(
        description="The name of an alternative technical option."
    )
    tradeoff: GeneratedTextStr = Field(
        description="The material benefits and costs of the alternative."
    )
    reason_not_selected: GeneratedTextStr = Field(
        description="Why the proposed solution is preferred over this option."
    )


class ArchitecturalDecision(StrictModel):
    component_name: GeneratedLabelStr = Field(
        description="The component or architectural layer being decided."
    )
    proposed_solution: GeneratedTextStr = Field(
        description="The recommended implementation for this component."
    )
    rationale: GeneratedTextStr = Field(
        description="Why this solution best fits the stated project goals."
    )
    alternatives: list[ArchitecturalAlternative] = Field(
        min_length=1,
        max_length=3,
        description="Viable alternatives considered for this decision.",
    )


class ClarifyingOption(StrictModel):
    label: GeneratedLabelStr = Field(
        description="A short user-facing choice label."
    )
    impact: GeneratedTextStr = Field(
        description="How selecting this option changes the blueprint."
    )


class ClarifyingQuestion(StrictModel):
    question_text: GeneratedTextStr = Field(
        description="A Socratic question requiring a meaningful design choice."
    )
    why_this_matters: GeneratedTextStr = Field(
        description="How the answer affects the project or its implementation."
    )
    suggested_options: list[ClarifyingOption] = Field(
        min_length=2,
        max_length=3,
        description="Two or three concrete choices the user can evaluate.",
    )


class MicroTask(StrictModel):
    task_description: GeneratedTextStr = Field(
        description="One specific, independently executable implementation task."
    )
    complexity_level: Literal["Low", "Medium", "High"] = Field(
        description="The task's relative implementation complexity."
    )
    verification_steps: list[VerificationStepStr] = Field(
        min_length=1,
        max_length=5,
        description="Observable checks proving the task works as intended.",
    )


class RoadmapMilestone(StrictModel):
    phase_name: GeneratedLabelStr = Field(
        description="The ordered implementation phase name."
    )
    objective: GeneratedTextStr = Field(
        description="The outcome this milestone is intended to achieve."
    )
    expected_deliverable: GeneratedTextStr = Field(
        description="The concrete artifact or behavior produced by the phase."
    )
    micro_tasks: list[MicroTask] = Field(
        min_length=1,
        max_length=10,
        description="Sequential tasks required to complete this milestone.",
    )


class DiagnosticWarning(StrictModel):
    affected_component: GeneratedLabelStr = Field(
        description="The component or layer exposed to the risk."
    )
    severity: Literal["Low", "Medium", "High", "Critical"] = Field(
        description="The expected impact if the risk is not mitigated."
    )
    risk_identified: GeneratedTextStr = Field(
        description="A concrete technical, security, or delivery risk."
    )
    preventative_guidance: GeneratedTextStr = Field(
        description="A specific action that reduces or prevents the risk."
    )


class SynthesisBlueprint(StrictModel):
    synthesized_conceptual_model: ConceptualModel = Field(
        description="The distilled project identity, value, and scope boundary."
    )
    personalization_trace: PersonalizationTrace = Field(
        description="An auditable record of profile-grounded adaptations."
    )
    architectural_decisions: list[
        ArchitecturalDecision
    ] = Field(
        min_length=1,
        max_length=8,
        description="The blueprint's major technical decisions and trade-offs.",
    )
    socratic_clarifying_questions: list[ClarifyingQuestion] = Field(
        min_length=1,
        max_length=5,
        description="Unresolved choices that require the user's judgment.",
    )
    step_by_step_execution_roadmap: list[RoadmapMilestone] = Field(
        min_length=1,
        max_length=8,
        description="An ordered, verifiable implementation roadmap.",
    )
    diagnostic_warnings: list[DiagnosticWarning] = Field(
        default_factory=list,
        max_length=10,
        description="Material risks and concrete preventative guidance.",
    )


class SynthesisRequest(StrictModel):
    project_id: IdentifierStr
    session_id: IdentifierStr
    user_id: IdentifierStr
    source_text: SourceText


class SynthesisResponse(StrictModel):
    blueprint_id: NonEmptyStr
    blueprint: SynthesisBlueprint
