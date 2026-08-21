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

from memory_policy import MemoryCategory, MemoryValue, validate_memory_value
from schemas import ChatResponse


DEFAULT_MEMORY_ROUTING_FIXTURE_PATH = Path(
    "tests/fixtures/memory_routing_cases.json"
)
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
ExpectedRouting = Literal[
    "propose",
    "no_proposal",
    "clarify_without_proposal",
]
ManualSemanticReview = Literal["none", "clarification_quality"]
ExecutionMode = Literal["stateless", "stateful"]
StatePrecondition = Literal[
    "none",
    "active_identical_preference",
    "structured_memory_decision",
]
RoutingFindingCode = Literal[
    "missing_proposal",
    "unnecessary_proposal",
    "proposal_mismatch",
    "proposal_contract_mismatch",
    "multiple_proposals",
]


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ExpectedProposalDefinition(_StrictFixtureModel):
    category: MemoryCategory
    proposed_value: MemoryValue

    @model_validator(mode="after")
    def validate_category_value_pair(self) -> Self:
        self.proposed_value = validate_memory_value(
            self.category,
            self.proposed_value,
        )
        return self


class _ScenarioDefinition(_StrictFixtureModel):
    scenario_id: ScenarioId
    message: ScenarioMessage
    expected_routing: ExpectedRouting
    expected_proposal: _ExpectedProposalDefinition | None
    manual_semantic_review: ManualSemanticReview
    execution_mode: ExecutionMode
    state_precondition: StatePrecondition

    @model_validator(mode="after")
    def validate_scenario_contract(self) -> Self:
        expects_proposal = self.expected_routing == "propose"
        if expects_proposal != (self.expected_proposal is not None):
            raise ValueError(
                "Only proposal scenarios may define an expected proposal."
            )
        expects_clarification_review = (
            self.expected_routing == "clarify_without_proposal"
        )
        if expects_clarification_review != (
            self.manual_semantic_review == "clarification_quality"
        ):
            raise ValueError(
                "Clarification routing requires manual semantic review."
            )
        is_stateful = self.execution_mode == "stateful"
        has_precondition = self.state_precondition != "none"
        if is_stateful != has_precondition:
            raise ValueError(
                "Stateful scenarios require exactly one state precondition."
            )
        return self


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["1.0"]
    scenarios: list[_ScenarioDefinition] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_unique_scenario_ids(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Scenario IDs must be unique.")
        return self


@dataclass(frozen=True, slots=True)
class ExpectedProposal:
    category: MemoryCategory
    proposed_value: MemoryValue


@dataclass(frozen=True, slots=True)
class MemoryRoutingScenario:
    scenario_id: str
    fixture_version: str
    message: str
    expected_routing: ExpectedRouting
    expected_proposal: ExpectedProposal | None
    manual_semantic_review: ManualSemanticReview
    execution_mode: ExecutionMode
    state_precondition: StatePrecondition


@dataclass(frozen=True, slots=True)
class RoutingFinding:
    code: RoutingFindingCode


def load_routing_scenarios(
    fixture_path: Path,
) -> tuple[MemoryRoutingScenario, ...]:
    """Load and validate the versioned memory-routing fixture."""
    document = _FixtureDocument.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        MemoryRoutingScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            message=scenario.message,
            expected_routing=scenario.expected_routing,
            expected_proposal=(
                ExpectedProposal(
                    category=scenario.expected_proposal.category,
                    proposed_value=(
                        scenario.expected_proposal.proposed_value
                    ),
                )
                if scenario.expected_proposal is not None
                else None
            ),
            manual_semantic_review=scenario.manual_semantic_review,
            execution_mode=scenario.execution_mode,
            state_precondition=scenario.state_precondition,
        )
        for scenario in document.scenarios
    )


def evaluate_routing(
    scenario: MemoryRoutingScenario,
    response: ChatResponse,
) -> tuple[RoutingFinding, ...]:
    """Evaluate only typed proposal evidence from one chat response."""
    proposal_action_count = sum(
        action.action_name == "propose_memory_signal"
        for action in response.actions
    )
    proposal_count = len(response.memory_proposals)
    if proposal_action_count > 1 or proposal_count > 1:
        return (RoutingFinding(code="multiple_proposals"),)
    if proposal_action_count != proposal_count:
        return (RoutingFinding(code="proposal_contract_mismatch"),)

    if scenario.expected_routing == "propose":
        if proposal_count == 0:
            return (RoutingFinding(code="missing_proposal"),)
        expected = scenario.expected_proposal
        if expected is None:
            return (RoutingFinding(code="proposal_contract_mismatch"),)
        actual = response.memory_proposals[0]
        if (
            actual.category != expected.category
            or actual.proposed_value != expected.proposed_value
        ):
            return (RoutingFinding(code="proposal_mismatch"),)
        return ()

    if proposal_count:
        return (RoutingFinding(code="unnecessary_proposal"),)
    return ()
