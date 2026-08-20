from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from blueprint_validation import (
    BlueprintValidationError,
    validate_blueprint,
)
from schemas import SourceText, SynthesisBlueprint
from synthesis import ALLOWED_PROFILE_KEYS


DEFAULT_QUALITY_FIXTURE_PATH = Path(
    "tests/fixtures/synthesis_quality_cases.json"
)
QualityPhrase = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ScenarioId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9-]+$",
    ),
]
ConceptId = ScenarioId


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _RequiredConceptDefinition(_StrictFixtureModel):
    concept_id: ConceptId
    phrases: list[QualityPhrase] = Field(min_length=1, max_length=8)


class _ScenarioDefinition(_StrictFixtureModel):
    scenario_id: ScenarioId
    source_text: SourceText
    profile: dict[str, object]
    required_concepts: list[_RequiredConceptDefinition] = Field(
        default_factory=list,
        max_length=12,
    )
    forbidden_claims: list[QualityPhrase] = Field(
        default_factory=list,
        max_length=12,
    )
    expected_adaptation_keys: list[QualityPhrase] = Field(
        default_factory=list,
        max_length=8,
    )
    min_architectural_decisions: int = Field(ge=0, le=8)
    max_architectural_decisions: int = Field(ge=0, le=8)
    min_clarifying_questions: int = Field(ge=0, le=5)
    max_clarifying_questions: int = Field(ge=0, le=5)
    min_roadmap_milestones: int = Field(ge=0, le=8)
    max_roadmap_milestones: int = Field(ge=0, le=8)
    min_diagnostic_warnings: int = Field(ge=0, le=10)
    max_diagnostic_warnings: int = Field(ge=0, le=10)

    @model_validator(mode="after")
    def validate_scenario_contract(self) -> Self:
        concept_ids = [
            concept.concept_id for concept in self.required_concepts
        ]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("Required concept IDs must be unique.")
        profile_keys = set(self.profile)
        if not profile_keys.issubset(ALLOWED_PROFILE_KEYS):
            raise ValueError("Scenario profile contains an unsupported key.")
        expected_keys = set(self.expected_adaptation_keys)
        if len(expected_keys) != len(self.expected_adaptation_keys):
            raise ValueError("Expected adaptation keys must be unique.")
        if not expected_keys.issubset(profile_keys):
            raise ValueError("Expected adaptation key is absent from profile.")
        bounds = (
            (
                self.min_architectural_decisions,
                self.max_architectural_decisions,
            ),
            (
                self.min_clarifying_questions,
                self.max_clarifying_questions,
            ),
            (
                self.min_roadmap_milestones,
                self.max_roadmap_milestones,
            ),
            (
                self.min_diagnostic_warnings,
                self.max_diagnostic_warnings,
            ),
        )
        if any(minimum > maximum for minimum, maximum in bounds):
            raise ValueError("Scenario minimum exceeds its maximum.")
        return self


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["1.1"]
    scenarios: list[_ScenarioDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_scenario_ids(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Scenario IDs must be unique.")
        return self


@dataclass(frozen=True)
class RequiredConcept:
    concept_id: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class QualityScenario:
    scenario_id: str
    fixture_version: str
    source_text: str
    profile: dict[str, object]
    required_concepts: tuple[RequiredConcept, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    expected_adaptation_keys: tuple[str, ...] = ()
    min_architectural_decisions: int | None = None
    max_architectural_decisions: int | None = None
    min_clarifying_questions: int | None = None
    max_clarifying_questions: int | None = None
    min_roadmap_milestones: int | None = None
    max_roadmap_milestones: int | None = None
    min_diagnostic_warnings: int | None = None
    max_diagnostic_warnings: int | None = None


@dataclass(frozen=True)
class QualityFinding:
    code: str


def load_quality_scenarios(
    path: Path = DEFAULT_QUALITY_FIXTURE_PATH,
) -> tuple[QualityScenario, ...]:
    """Load and strictly validate versioned quality scenarios."""
    document = _FixtureDocument.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    return tuple(
        QualityScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            source_text=scenario.source_text,
            profile=dict(scenario.profile),
            required_concepts=tuple(
                RequiredConcept(
                    concept_id=concept.concept_id,
                    phrases=tuple(concept.phrases),
                )
                for concept in scenario.required_concepts
            ),
            forbidden_claims=tuple(scenario.forbidden_claims),
            expected_adaptation_keys=tuple(
                scenario.expected_adaptation_keys
            ),
            min_architectural_decisions=(
                scenario.min_architectural_decisions
            ),
            max_architectural_decisions=(
                scenario.max_architectural_decisions
            ),
            min_clarifying_questions=scenario.min_clarifying_questions,
            max_clarifying_questions=scenario.max_clarifying_questions,
            min_roadmap_milestones=scenario.min_roadmap_milestones,
            max_roadmap_milestones=scenario.max_roadmap_milestones,
            min_diagnostic_warnings=scenario.min_diagnostic_warnings,
            max_diagnostic_warnings=scenario.max_diagnostic_warnings,
        )
        for scenario in document.scenarios
    )


def evaluate_blueprint(
    scenario: QualityScenario,
    blueprint: SynthesisBlueprint,
) -> tuple[QualityFinding, ...]:
    """Evaluate deterministic quality requirements for one blueprint."""
    try:
        validate_blueprint(blueprint, scenario.profile)
    except BlueprintValidationError:
        return (QualityFinding(code="invalid_blueprint"),)

    serialized = blueprint.model_dump_json().casefold()
    findings = [
        QualityFinding(
            code=f"missing_required_concept:{concept.concept_id}"
        )
        for concept in scenario.required_concepts
        if not any(
            phrase.casefold() in serialized
            for phrase in concept.phrases
        )
    ]
    findings.extend(
        QualityFinding(code="forbidden_claim")
        for phrase in scenario.forbidden_claims
        if phrase.casefold() in serialized
    )
    actual_adaptation_keys = {
        adaptation.profile_key
        for adaptation in blueprint.personalization_trace.adaptations
    }
    expected_adaptation_keys = set(scenario.expected_adaptation_keys)
    if not expected_adaptation_keys.issubset(
        actual_adaptation_keys
    ):
        findings.append(
            QualityFinding(code="missing_expected_adaptation")
        )
    if not actual_adaptation_keys.issubset(expected_adaptation_keys):
        findings.append(
            QualityFinding(code="unexpected_adaptation")
        )
    structural_counts = (
        (
            len(blueprint.architectural_decisions),
            scenario.min_architectural_decisions,
            scenario.max_architectural_decisions,
            "too_few_decisions",
            "too_many_decisions",
        ),
        (
            len(blueprint.socratic_clarifying_questions),
            scenario.min_clarifying_questions,
            scenario.max_clarifying_questions,
            "too_few_questions",
            "too_many_questions",
        ),
        (
            len(blueprint.step_by_step_execution_roadmap),
            scenario.min_roadmap_milestones,
            scenario.max_roadmap_milestones,
            "too_few_milestones",
            "too_many_milestones",
        ),
        (
            len(blueprint.diagnostic_warnings),
            scenario.min_diagnostic_warnings,
            scenario.max_diagnostic_warnings,
            "too_few_warnings",
            "too_many_warnings",
        ),
    )
    for count, minimum, maximum, too_few_code, too_many_code in (
        structural_counts
    ):
        if minimum is not None and count < minimum:
            findings.append(QualityFinding(code=too_few_code))
        if maximum is not None and count > maximum:
            findings.append(QualityFinding(code=too_many_code))
    return tuple(findings)
