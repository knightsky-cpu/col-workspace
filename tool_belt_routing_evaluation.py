"""Strict decision-only evaluation contracts for Agent_Col's tool belt."""

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

from agent_col_numeric_projection import (
    RoutingNumericId,
    project_routing_numeric_candidates,
)
from agent_col_routing import RoutingUrlId, project_routing_url_candidates
from agent_col_routing_v2 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
)
from computational_expert import PrecisionRule
from expert_contracts import ExpertCapability


DEFAULT_TOOL_BELT_ROUTING_FIXTURE_PATH = Path(
    "tests/fixtures/agent_col_tool_belt_routing_cases.json"
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
ManualSemanticReview = Literal[
    "none",
    "clarification_quality",
    "cross_capability_quality",
]
ExpectedPrecisionMode = Literal[
    "decimal_places",
    "significant_figures",
]
ToolBeltRoutingFindingCode = Literal[
    "unnecessary_expert",
    "missing_expert",
    "wrong_expert",
    "route_mismatch",
    "url_selection_mismatch",
    "scalar_selection_mismatch",
    "series_selection_mismatch",
    "precision_selection_mismatch",
]


class _StrictFixtureModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class _ScenarioDefinition(_StrictFixtureModel):
    scenario_id: ScenarioId
    message: ScenarioMessage
    expected_route: AgentColRoute
    expected_url_ids: tuple[RoutingUrlId, ...] = Field(
        default_factory=tuple,
        max_length=3,
    )
    expected_scalar_numeric_ids: tuple[RoutingNumericId, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    expected_series_numeric_ids: tuple[
        tuple[RoutingNumericId, ...], ...
    ] = Field(default_factory=tuple, max_length=8)
    expected_precision_numeric_id: RoutingNumericId | None = None
    expected_precision_mode: ExpectedPrecisionMode | None = None
    manual_semantic_review: ManualSemanticReview = "none"

    @model_validator(mode="after")
    def require_coherent_expected_decision(self) -> Self:
        routing_input = _build_routing_input(self.message)
        available_url_ids = {
            candidate.candidate_id
            for candidate in routing_input.candidate_urls
        }
        url_order = {
            candidate.candidate_id: index
            for index, candidate in enumerate(routing_input.candidate_urls)
        }
        numeric_candidates_by_id = {
            candidate.candidate_id: candidate
            for candidate in routing_input.numeric_candidates
        }
        numeric_order = {
            candidate.candidate_id: index
            for index, candidate in enumerate(routing_input.numeric_candidates)
        }

        if self.expected_route is AgentColRoute.SOURCE:
            if not self.expected_url_ids:
                raise ValueError("Source scenarios require selected URLs.")
        elif self.expected_url_ids:
            raise ValueError("Only source scenarios may select URLs.")
        if not set(self.expected_url_ids) <= available_url_ids:
            raise ValueError("Expected URL ID is not in the routing input.")
        if len(set(self.expected_url_ids)) != len(self.expected_url_ids):
            raise ValueError("Expected URL IDs must be unique.")
        expected_url_order = tuple(
            url_order[url_id] for url_id in self.expected_url_ids
        )
        if expected_url_order != tuple(sorted(expected_url_order)):
            raise ValueError("Expected URL IDs must preserve source order.")

        operand_ids = tuple(self.expected_scalar_numeric_ids) + tuple(
            numeric_id
            for group in self.expected_series_numeric_ids
            for numeric_id in group
        )
        has_computation_selection = bool(
            operand_ids or self.expected_precision_numeric_id
        )
        if self.expected_route is AgentColRoute.COMPUTATION:
            if not operand_ids:
                raise ValueError(
                    "Computation scenarios require at least one operand."
                )
            if routing_input.numeric_projection_incomplete:
                raise ValueError(
                    "Computation scenarios require a complete projection."
                )
        elif has_computation_selection:
            raise ValueError(
                "Only computation scenarios may select numeric candidates."
            )
        if any(not group for group in self.expected_series_numeric_ids):
            raise ValueError("Expected computation series cannot be empty.")
        if len(set(operand_ids)) != len(operand_ids):
            raise ValueError("Expected computation operands must be unique.")
        selected_numeric_ids = set(operand_ids)
        if (self.expected_precision_numeric_id is None) != (
            self.expected_precision_mode is None
        ):
            raise ValueError(
                "Precision candidate and mode must be defined together."
            )
        if self.expected_precision_numeric_id is not None:
            if self.expected_precision_numeric_id in selected_numeric_ids:
                raise ValueError("Precision cannot also be an operand.")
            selected_numeric_ids.add(self.expected_precision_numeric_id)
        if not selected_numeric_ids <= set(numeric_candidates_by_id):
            raise ValueError(
                "Expected numeric ID is not in the routing input."
            )
        for group in self.expected_series_numeric_ids:
            group_order = tuple(
                numeric_order[numeric_id] for numeric_id in group
            )
            if group_order != tuple(sorted(group_order)):
                raise ValueError(
                    "Expected computation series must preserve source order."
                )
            units = {
                (
                    numeric_candidates_by_id[numeric_id].notation,
                    numeric_candidates_by_id[numeric_id].unit_symbol,
                )
                for numeric_id in group
            }
            if len(units) != 1:
                raise ValueError(
                    "Expected computation series units are incompatible."
                )
        if self.expected_precision_numeric_id is not None:
            precision_value = numeric_candidates_by_id[
                self.expected_precision_numeric_id
            ].value
            if not precision_value.is_integer():
                raise ValueError("Expected precision must be an integer.")
            PrecisionRule(
                mode=self.expected_precision_mode,
                digits=int(precision_value),
            )

        requires_review = self.expected_route is AgentColRoute.CLARIFY
        has_review = self.manual_semantic_review != "none"
        if requires_review != has_review:
            raise ValueError(
                "Clarification scenarios require semantic review only."
            )
        if (
            self.manual_semantic_review == "cross_capability_quality"
            and self.expected_route is not AgentColRoute.CLARIFY
        ):
            raise ValueError(
                "Cross-capability review requires a clarification route."
            )
        return self


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["1.0"]
    scenarios: tuple[_ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def require_unique_scenario_ids(self) -> Self:
        scenario_ids = tuple(
            scenario.scenario_id for scenario in self.scenarios
        )
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("Fixture scenario IDs must be unique.")
        return self


@dataclass(frozen=True, slots=True)
class ToolBeltRoutingScenario:
    scenario_id: str
    fixture_version: str
    message: str
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute
    expected_url_ids: tuple[str, ...]
    expected_scalar_numeric_ids: tuple[str, ...]
    expected_series_numeric_ids: tuple[tuple[str, ...], ...]
    expected_precision_numeric_id: str | None
    expected_precision_mode: ExpectedPrecisionMode | None
    manual_semantic_review: ManualSemanticReview


@dataclass(frozen=True, slots=True)
class ToolBeltRoutingFinding:
    code: ToolBeltRoutingFindingCode


def _build_routing_input(message: str) -> AgentColRoutingInput:
    numeric_projection = project_routing_numeric_candidates(message)
    return AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric_projection.candidates,
        numeric_projection_incomplete=(
            numeric_projection.numeric_projection_incomplete
        ),
        available_capabilities=(
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
            ExpertCapability.COMPUTATION,
        ),
    )


def load_tool_belt_routing_scenarios(
    fixture_path: Path,
) -> tuple[ToolBeltRoutingScenario, ...]:
    """Load scenarios and derive their exact production routing inputs."""
    document = _FixtureDocument.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        ToolBeltRoutingScenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            message=scenario.message,
            routing_input=_build_routing_input(scenario.message),
            expected_route=scenario.expected_route,
            expected_url_ids=tuple(scenario.expected_url_ids),
            expected_scalar_numeric_ids=tuple(
                scenario.expected_scalar_numeric_ids
            ),
            expected_series_numeric_ids=tuple(
                tuple(group)
                for group in scenario.expected_series_numeric_ids
            ),
            expected_precision_numeric_id=(
                scenario.expected_precision_numeric_id
            ),
            expected_precision_mode=scenario.expected_precision_mode,
            manual_semantic_review=scenario.manual_semantic_review,
        )
        for scenario in document.scenarios
    )


def _classify_route_mismatch(
    expected_route: AgentColRoute,
    actual_route: AgentColRoute,
) -> ToolBeltRoutingFindingCode:
    expert_routes = {
        AgentColRoute.SOURCE,
        AgentColRoute.RESEARCH,
        AgentColRoute.COMPUTATION,
    }
    if expected_route is AgentColRoute.DIRECT and actual_route in expert_routes:
        return "unnecessary_expert"
    if expected_route in expert_routes and actual_route not in expert_routes:
        return "missing_expert"
    if expected_route in expert_routes and actual_route in expert_routes:
        return "wrong_expert"
    return "route_mismatch"


def evaluate_tool_belt_routing(
    scenario: ToolBeltRoutingScenario,
    directive: AgentColRoutingDirective,
) -> tuple[ToolBeltRoutingFinding, ...]:
    """Evaluate one validated decision without executing any expert."""
    if directive.route is not scenario.expected_route:
        return (
            ToolBeltRoutingFinding(
                code=_classify_route_mismatch(
                    scenario.expected_route,
                    directive.route,
                )
            ),
        )

    if directive.route is AgentColRoute.SOURCE:
        assert directive.source_intent is not None
        if set(directive.source_intent.selected_url_ids) != set(
            scenario.expected_url_ids
        ):
            return (
                ToolBeltRoutingFinding(code="url_selection_mismatch"),
            )
        return ()

    if directive.route is not AgentColRoute.COMPUTATION:
        return ()

    assert directive.computation_intent is not None
    intent = directive.computation_intent
    findings: list[ToolBeltRoutingFinding] = []
    scalar_ids = tuple(
        selection.numeric_id for selection in intent.scalar_inputs
    )
    if set(scalar_ids) != set(scenario.expected_scalar_numeric_ids):
        findings.append(
            ToolBeltRoutingFinding(code="scalar_selection_mismatch")
        )
    series_ids = tuple(
        tuple(selection.numeric_ids) for selection in intent.series_inputs
    )
    if set(series_ids) != set(scenario.expected_series_numeric_ids):
        findings.append(
            ToolBeltRoutingFinding(code="series_selection_mismatch")
        )
    precision_id = (
        intent.precision.digits_numeric_id
        if intent.precision is not None
        else None
    )
    precision_mode = (
        intent.precision.mode if intent.precision is not None else None
    )
    if (
        precision_id,
        precision_mode,
    ) != (
        scenario.expected_precision_numeric_id,
        scenario.expected_precision_mode,
    ):
        findings.append(
            ToolBeltRoutingFinding(code="precision_selection_mismatch")
        )
    return tuple(findings)
