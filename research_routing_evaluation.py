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

from schemas import ChatResponse


DEFAULT_RESEARCH_ROUTING_FIXTURE_PATH = Path(
    "tests/fixtures/research_routing_cases.json"
)
ExpectedResearchRouting = Literal["research", "direct", "clarify"]
ResearchExecutionMode = Literal["single", "idempotency_replay"]
ResearchSemanticReview = Literal[
    "none",
    "clarification_quality",
    "source_boundary_quality",
]
ResearchRoutingFindingCode = Literal[
    "missing_research_action",
    "missing_citations",
    "multiple_research_actions",
    "unnecessary_research",
    "unexpected_citations",
    "replay_mismatch",
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
ScenarioMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ScenarioDefinition(_StrictFixtureModel):
    scenario_id: ScenarioId
    message: ScenarioMessage
    expected_routing: ExpectedResearchRouting
    manual_semantic_review: ResearchSemanticReview
    execution_mode: ResearchExecutionMode

    @model_validator(mode="after")
    def validate_scenario_contract(self) -> Self:
        expects_clarification = self.expected_routing == "clarify"
        if expects_clarification != (
            self.manual_semantic_review == "clarification_quality"
        ):
            raise ValueError(
                "Clarification routing requires manual semantic review."
            )
        if (
            self.manual_semantic_review == "source_boundary_quality"
            and self.expected_routing != "direct"
        ):
            raise ValueError(
                "Source-boundary review requires direct routing."
            )
        if (
            self.execution_mode == "idempotency_replay"
            and self.expected_routing != "research"
        ):
            raise ValueError(
                "Idempotency replay must evaluate a Research route."
            )
        return self


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["1.0"]
    scenarios: tuple[_ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_unique_scenario_ids(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Research routing scenario IDs must be unique.")
        return self


@dataclass(frozen=True, slots=True)
class ResearchRoutingScenario:
    scenario_id: str
    fixture_version: str
    message: str
    expected_routing: ExpectedResearchRouting
    manual_semantic_review: ResearchSemanticReview
    execution_mode: ResearchExecutionMode


@dataclass(frozen=True, slots=True)
class ResearchRoutingFinding:
    code: ResearchRoutingFindingCode


def load_research_routing_scenarios(
    fixture_path: Path,
) -> tuple[ResearchRoutingScenario, ...]:
    """Load and validate the versioned Research routing fixture."""
    document = _FixtureDocument.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        ResearchRoutingScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            message=scenario.message,
            expected_routing=scenario.expected_routing,
            manual_semantic_review=scenario.manual_semantic_review,
            execution_mode=scenario.execution_mode,
        )
        for scenario in document.scenarios
    )


def evaluate_research_routing(
    scenario: ResearchRoutingScenario,
    responses: tuple[ChatResponse, ...],
) -> tuple[ResearchRoutingFinding, ...]:
    """Evaluate typed Research receipts and idempotent replay evidence."""
    response = responses[0]
    search_action_count = sum(
        action.action_name == "google_search"
        for action in response.actions
    )
    if search_action_count > 1:
        return (
            ResearchRoutingFinding(code="multiple_research_actions"),
        )
    if scenario.expected_routing == "research":
        if search_action_count == 0:
            return (ResearchRoutingFinding(code="missing_research_action"),)
        if not response.citations:
            return (ResearchRoutingFinding(code="missing_citations"),)
    else:
        if search_action_count:
            return (ResearchRoutingFinding(code="unnecessary_research"),)
        if response.citations:
            return (ResearchRoutingFinding(code="unexpected_citations"),)

    if scenario.execution_mode == "idempotency_replay" and (
        len(responses) != 2 or responses[0] != responses[1]
    ):
        return (ResearchRoutingFinding(code="replay_mismatch"),)
    return ()
