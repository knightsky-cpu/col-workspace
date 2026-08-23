"""Offline routing-v3 evaluation contracts for Agent_Col's tool belt."""

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
from agent_col_routing_v3 import (
    AgentColRoute,
    AgentColRoutingDirective,
    AgentColRoutingInput,
    RoutingDirectiveInputError,
    validate_routing_directive_for_input,
)
from agent_col_text_projection import (
    RoutingTextBlockId,
    project_routing_text_blocks,
)
from expert_contracts import ExpertCapability


DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH = Path(
    "tests/fixtures/agent_col_tool_belt_routing_v3_cases.json"
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
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]
ScenarioRationale = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
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
SafetyClass = Literal["standard", "hard_invariant"]
LiveRepetitions = Literal[1, 3, 5]
ToolBeltRoutingV3FindingCode = Literal[
    "unsafe_route",
    "unnecessary_expert",
    "missing_expert",
    "wrong_expert",
    "route_mismatch",
    "url_selection_mismatch",
    "scalar_selection_mismatch",
    "series_selection_mismatch",
    "precision_selection_mismatch",
    "requirement_selection_mismatch",
    "subject_selection_mismatch",
]

_EXPERT_ROUTES = frozenset(
    {
        AgentColRoute.SOURCE,
        AgentColRoute.RESEARCH,
        AgentColRoute.COMPUTATION,
        AgentColRoute.REQUIREMENTS_VERIFICATION,
    }
)


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
    expected_requirement_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=50,
    )
    expected_subject_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    safety_class: SafetyClass
    live_repetitions: LiveRepetitions
    manual_semantic_review: ManualSemanticReview
    rationale: ScenarioRationale

    @model_validator(mode="after")
    def require_coherent_expected_decision(self) -> Self:
        routing_input = _build_routing_v3_input(self.message)
        self._require_route_specific_selections()
        self._require_canonical_url_selection(routing_input)
        self._require_review_and_repetition_policy()
        directive = self._build_expected_directive()
        try:
            validate_routing_directive_for_input(directive, routing_input)
        except RoutingDirectiveInputError as exc:
            raise ValueError(
                "Scenario expectation is incompatible with its projection."
            ) from exc
        return self

    def _require_route_specific_selections(self) -> None:
        has_url_selection = bool(self.expected_url_ids)
        numeric_ids = tuple(self.expected_scalar_numeric_ids) + tuple(
            numeric_id
            for group in self.expected_series_numeric_ids
            for numeric_id in group
        )
        has_numeric_selection = bool(
            numeric_ids or self.expected_precision_numeric_id
        )
        has_text_selection = bool(
            self.expected_requirement_block_ids
            or self.expected_subject_block_ids
        )

        if self.expected_route is AgentColRoute.SOURCE:
            if not has_url_selection:
                raise ValueError("Source scenarios require selected URLs.")
        elif has_url_selection:
            raise ValueError("Only Source scenarios may select URLs.")

        if self.expected_route is AgentColRoute.COMPUTATION:
            if not numeric_ids:
                raise ValueError(
                    "Computation scenarios require at least one operand."
                )
        elif has_numeric_selection or self.expected_precision_mode is not None:
            raise ValueError(
                "Only Computation scenarios may select numeric candidates."
            )

        has_precision_id = self.expected_precision_numeric_id is not None
        has_precision_mode = self.expected_precision_mode is not None
        if has_precision_id != has_precision_mode:
            raise ValueError(
                "Precision candidate and mode must be defined together."
            )

        if self.expected_route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            if not self.expected_requirement_block_ids:
                raise ValueError(
                    "Requirements Verification requires requirements."
                )
            if not self.expected_subject_block_ids:
                raise ValueError(
                    "Requirements Verification requires a subject."
                )
        elif has_text_selection:
            raise ValueError(
                "Only Requirements Verification may select text blocks."
            )

    def _require_canonical_url_selection(
        self,
        routing_input: AgentColRoutingInput,
    ) -> None:
        available_order = {
            candidate.candidate_id: index
            for index, candidate in enumerate(routing_input.candidate_urls)
        }
        if len(set(self.expected_url_ids)) != len(self.expected_url_ids):
            raise ValueError("Expected URL IDs must be unique.")
        if not set(self.expected_url_ids) <= set(available_order):
            raise ValueError("Expected URL ID is not in the routing input.")
        selected_order = tuple(
            available_order[candidate_id]
            for candidate_id in self.expected_url_ids
        )
        if selected_order != tuple(sorted(selected_order)):
            raise ValueError("Expected URL IDs must preserve source order.")

    def _require_review_and_repetition_policy(self) -> None:
        requires_review = self.expected_route is AgentColRoute.CLARIFY
        has_review = self.manual_semantic_review != "none"
        if requires_review != has_review:
            raise ValueError(
                "Clarification scenarios require semantic review only."
            )
        if self.manual_semantic_review == "cross_capability_quality" and (
            self.expected_route is not AgentColRoute.CLARIFY
            or self.safety_class != "hard_invariant"
        ):
            raise ValueError(
                "Cross-capability review requires a hard clarification."
            )

        expert_routes = {
            AgentColRoute.SOURCE,
            AgentColRoute.RESEARCH,
            AgentColRoute.COMPUTATION,
            AgentColRoute.REQUIREMENTS_VERIFICATION,
        }
        if self.expected_route in expert_routes:
            if self.safety_class != "standard":
                raise ValueError("Expert scenarios use standard safety class.")
            expected_repetitions = 3
        elif self.safety_class == "hard_invariant":
            expected_repetitions = 5
        else:
            expected_repetitions = 1
        if self.live_repetitions != expected_repetitions:
            raise ValueError(
                "Scenario live repetitions do not match its class."
            )

    def _build_expected_directive(self) -> AgentColRoutingDirective:
        payload: dict[str, object] = {
            "schema_version": "3.0",
            "route": self.expected_route,
        }
        if self.expected_route is AgentColRoute.CLARIFY:
            payload["clarifying_question"] = (
                "What material information should Agent_Col use?"
            )
        elif self.expected_route is AgentColRoute.SOURCE:
            payload["source_intent"] = {
                "objective": "Analyze the selected synthetic sources.",
                "selected_url_ids": self.expected_url_ids,
                "constraints": (),
            }
        elif self.expected_route is AgentColRoute.RESEARCH:
            payload["research_intent"] = {
                "question": "What current public evidence answers the task?",
                "objective": "Find current public evidence.",
                "constraints": (),
            }
        elif self.expected_route is AgentColRoute.COMPUTATION:
            payload["computation_intent"] = {
                "objective": "Calculate using the selected values.",
                "scalar_inputs": tuple(
                    {
                        "name": f"value_{index}",
                        "numeric_id": numeric_id,
                    }
                    for index, numeric_id in enumerate(
                        self.expected_scalar_numeric_ids,
                        start=1,
                    )
                ),
                "series_inputs": tuple(
                    {
                        "name": f"series_{index}",
                        "numeric_ids": group,
                    }
                    for index, group in enumerate(
                        self.expected_series_numeric_ids,
                        start=1,
                    )
                ),
                "precision": (
                    {
                        "mode": self.expected_precision_mode,
                        "digits_numeric_id": (
                            self.expected_precision_numeric_id
                        ),
                    }
                    if self.expected_precision_numeric_id is not None
                    else None
                ),
                "constraints": (),
            }
        elif self.expected_route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            payload["requirements_verification_intent"] = {
                "objective": "Compare the selected synthetic material.",
                "requirement_block_ids": (
                    self.expected_requirement_block_ids
                ),
                "subject_block_ids": self.expected_subject_block_ids,
                "constraints": (),
            }
        return AgentColRoutingDirective.model_validate(payload)


class _FixtureDocument(_StrictFixtureModel):
    fixture_version: Literal["3.0"]
    scenarios: tuple[_ScenarioDefinition, ...] = Field(
        min_length=1,
        max_length=40,
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
class ToolBeltRoutingV3Scenario:
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
    expected_requirement_block_ids: tuple[str, ...]
    expected_subject_block_ids: tuple[str, ...]
    safety_class: SafetyClass
    live_repetitions: LiveRepetitions
    manual_semantic_review: ManualSemanticReview
    rationale: str


@dataclass(frozen=True, slots=True)
class ToolBeltRoutingV3Finding:
    code: ToolBeltRoutingV3FindingCode


def _classify_route_mismatch(
    scenario: ToolBeltRoutingV3Scenario,
    actual_route: AgentColRoute,
) -> ToolBeltRoutingV3FindingCode:
    expected_route = scenario.expected_route
    actual_is_expert = actual_route in _EXPERT_ROUTES
    expected_is_expert = expected_route in _EXPERT_ROUTES
    if (
        scenario.safety_class == "hard_invariant"
        and not expected_is_expert
        and actual_is_expert
    ):
        return "unsafe_route"
    if expected_route is AgentColRoute.DIRECT and actual_is_expert:
        return "unnecessary_expert"
    if expected_is_expert and not actual_is_expert:
        return "missing_expert"
    if expected_is_expert and actual_is_expert:
        return "wrong_expert"
    return "route_mismatch"


def evaluate_tool_belt_routing_v3(
    scenario: ToolBeltRoutingV3Scenario,
    actual: AgentColRoutingDirective,
) -> tuple[ToolBeltRoutingV3Finding, ...]:
    """Classify an observed routing decision without retaining user content."""
    if actual.route is scenario.expected_route:
        findings: list[ToolBeltRoutingV3Finding] = []
        if actual.route is AgentColRoute.SOURCE:
            assert actual.source_intent is not None
            if set(actual.source_intent.selected_url_ids) != set(
                scenario.expected_url_ids
            ):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="url_selection_mismatch"
                    )
                )
        elif actual.route is AgentColRoute.COMPUTATION:
            assert actual.computation_intent is not None
            intent = actual.computation_intent
            scalar_ids = {
                selection.numeric_id for selection in intent.scalar_inputs
            }
            if scalar_ids != set(scenario.expected_scalar_numeric_ids):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="scalar_selection_mismatch"
                    )
                )
            series_ids = {
                tuple(selection.numeric_ids)
                for selection in intent.series_inputs
            }
            if series_ids != set(scenario.expected_series_numeric_ids):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="series_selection_mismatch"
                    )
                )
            precision = (
                (
                    intent.precision.digits_numeric_id,
                    intent.precision.mode,
                )
                if intent.precision is not None
                else (None, None)
            )
            if precision != (
                scenario.expected_precision_numeric_id,
                scenario.expected_precision_mode,
            ):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="precision_selection_mismatch"
                    )
                )
        elif actual.route is AgentColRoute.REQUIREMENTS_VERIFICATION:
            assert actual.requirements_verification_intent is not None
            intent = actual.requirements_verification_intent
            if tuple(intent.requirement_block_ids) != (
                scenario.expected_requirement_block_ids
            ):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="requirement_selection_mismatch"
                    )
                )
            if tuple(intent.subject_block_ids) != (
                scenario.expected_subject_block_ids
            ):
                findings.append(
                    ToolBeltRoutingV3Finding(
                        code="subject_selection_mismatch"
                    )
                )
        return tuple(findings)
    return (
        ToolBeltRoutingV3Finding(
            code=_classify_route_mismatch(scenario, actual.route)
        ),
    )


def _build_routing_v3_input(message: str) -> AgentColRoutingInput:
    numeric = project_routing_numeric_candidates(message)
    text = project_routing_text_blocks(message)
    return AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric.candidates,
        numeric_projection_incomplete=numeric.numeric_projection_incomplete,
        text_block_candidates=text.candidates,
        text_projection_incomplete=text.text_projection_incomplete,
        available_capabilities=(
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
            ExpertCapability.COMPUTATION,
            ExpertCapability.REQUIREMENTS_VERIFICATION,
        ),
    )


def load_tool_belt_routing_v3_scenarios(
    fixture_path: Path,
) -> tuple[ToolBeltRoutingV3Scenario, ...]:
    """Load v3 scenarios and derive their production routing inputs."""
    document = _FixtureDocument.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    return tuple(
        ToolBeltRoutingV3Scenario(
            scenario_id=scenario.scenario_id,
            fixture_version=document.fixture_version,
            message=scenario.message,
            routing_input=_build_routing_v3_input(scenario.message),
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
            expected_requirement_block_ids=tuple(
                scenario.expected_requirement_block_ids
            ),
            expected_subject_block_ids=tuple(
                scenario.expected_subject_block_ids
            ),
            safety_class=scenario.safety_class,
            live_repetitions=scenario.live_repetitions,
            manual_semantic_review=scenario.manual_semantic_review,
            rationale=scenario.rationale,
        )
        for scenario in document.scenarios
    )
