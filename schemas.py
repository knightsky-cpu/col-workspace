from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
)


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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentActionReceipt(StrictModel):
    action_name: Literal[
        "synthesize_project",
        "google_search",
        "url_context",
        "record_blueprint_feedback",
    ]
    status: Literal["completed"]


class ArtifactReference(StrictModel):
    artifact_type: Literal["synthesis_blueprint"]
    project_id: IdentifierStr
    artifact_id: IdentifierStr
    schema_version: Literal["1.0"]
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


class ConceptualModel(StrictModel):
    project_name: NonEmptyStr
    core_value_proposition: NonEmptyStr
    in_scope: list[NonEmptyStr] = Field(min_length=1)
    out_of_scope: list[NonEmptyStr] = Field(default_factory=list)
    assumptions: list[NonEmptyStr] = Field(default_factory=list)


class PersonalizationAdaptation(StrictModel):
    profile_key: NonEmptyStr
    architecture_change: NonEmptyStr
    reason: NonEmptyStr


class PersonalizationTrace(StrictModel):
    adaptations: list[PersonalizationAdaptation] = Field(
        default_factory=list
    )


class ArchitecturalAlternative(StrictModel):
    option_name: NonEmptyStr
    tradeoff: NonEmptyStr
    reason_not_selected: NonEmptyStr


class ArchitecturalDecision(StrictModel):
    component_name: NonEmptyStr
    proposed_solution: NonEmptyStr
    rationale: NonEmptyStr
    alternatives: list[ArchitecturalAlternative] = Field(min_length=1)


class ClarifyingOption(StrictModel):
    label: NonEmptyStr
    impact: NonEmptyStr


class ClarifyingQuestion(StrictModel):
    question_text: NonEmptyStr
    why_this_matters: NonEmptyStr
    suggested_options: list[ClarifyingOption] = Field(
        min_length=2,
        max_length=3,
    )


class MicroTask(StrictModel):
    task_description: NonEmptyStr
    complexity_level: Literal["Low", "Medium", "High"]
    verification_steps: list[NonEmptyStr] = Field(min_length=1)


class RoadmapMilestone(StrictModel):
    phase_name: NonEmptyStr
    objective: NonEmptyStr
    expected_deliverable: NonEmptyStr
    micro_tasks: list[MicroTask] = Field(min_length=1)


class DiagnosticWarning(StrictModel):
    affected_component: NonEmptyStr
    severity: Literal["Low", "Medium", "High", "Critical"]
    risk_identified: NonEmptyStr
    preventative_guidance: NonEmptyStr


class SynthesisBlueprint(StrictModel):
    synthesized_conceptual_model: ConceptualModel
    personalization_trace: PersonalizationTrace
    architectural_decisions_and_feedback: list[
        ArchitecturalDecision
    ] = Field(min_length=1)
    socratic_clarifying_questions: list[ClarifyingQuestion] = Field(
        min_length=1
    )
    step_by_step_execution_roadmap: list[RoadmapMilestone] = Field(
        min_length=1
    )
    diagnostic_warnings: list[DiagnosticWarning] = Field(
        default_factory=list
    )


class SynthesisRequest(StrictModel):
    project_id: IdentifierStr
    session_id: IdentifierStr
    user_id: IdentifierStr
    source_text: SourceText


class SynthesisResponse(StrictModel):
    blueprint_id: NonEmptyStr
    blueprint: SynthesisBlueprint
