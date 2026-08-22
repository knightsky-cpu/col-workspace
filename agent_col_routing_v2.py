"""Parallel Agent_Col routing v2 contracts for compatibility testing."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from agent_col_numeric_projection import (
    RoutingNumericCandidate,
    RoutingNumericId,
    contains_numeric_like_text,
)
from agent_col_routing import (
    RoutingClarificationText,
    RoutingConstraintText,
    RoutingMessageText,
    RoutingTaskText,
    RoutingUrlCandidate,
    RoutingUrlId,
)
from computational_expert import PrecisionRule, validate_computation_task_text
from expert_contracts import ExpertCapability


ComputationInputName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$"),
]


class AgentColRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    SOURCE = "source"
    RESEARCH = "research"
    COMPUTATION = "computation"


class RoutingDirectiveInputError(RuntimeError):
    """Raised when a valid v2 directive cannot execute against its input."""


class StrictRoutingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class AgentColRoutingInput(StrictRoutingModel):
    current_message: RoutingMessageText
    candidate_urls: tuple[RoutingUrlCandidate, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    numeric_candidates: tuple[RoutingNumericCandidate, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    numeric_projection_incomplete: bool = False
    available_capabilities: tuple[ExpertCapability, ...] = Field(
        default_factory=tuple,
        max_length=3,
    )

    @model_validator(mode="after")
    def require_valid_bounded_context(self) -> Self:
        allowed_capabilities = {
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
            ExpertCapability.COMPUTATION,
        }
        if not set(self.available_capabilities) <= allowed_capabilities:
            raise ValueError("Routing capability is not available.")
        if len(set(self.available_capabilities)) != len(
            self.available_capabilities
        ):
            raise ValueError("Routing capabilities must be unique.")

        candidate_url_ids = tuple(
            candidate.candidate_id for candidate in self.candidate_urls
        )
        candidate_urls = tuple(
            str(candidate.url) for candidate in self.candidate_urls
        )
        if len(set(candidate_url_ids)) != len(candidate_url_ids):
            raise ValueError("Routing candidate IDs must be unique.")
        if len(set(candidate_urls)) != len(candidate_urls):
            raise ValueError("Routing candidate URLs must be unique.")

        previous_end = -1
        for index, candidate in enumerate(self.numeric_candidates, start=1):
            if candidate.candidate_id != f"number-{index}":
                raise ValueError("Numeric candidate IDs must be sequential.")
            if (
                self.current_message[
                    candidate.start_index:candidate.end_index
                ]
                != candidate.raw_text
            ):
                raise ValueError("Numeric candidate span does not match input.")
            if candidate.start_index < previous_end:
                raise ValueError("Numeric candidate spans must not overlap.")
            previous_end = candidate.end_index
        return self


class SourceRoutingIntent(StrictRoutingModel):
    objective: RoutingTaskText
    selected_url_ids: tuple[RoutingUrlId, ...] = Field(
        min_length=1,
        max_length=3,
    )
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_unique_url_ids(self) -> Self:
        if len(set(self.selected_url_ids)) != len(self.selected_url_ids):
            raise ValueError("Selected routing URL IDs must be unique.")
        return self


class ResearchRoutingIntent(StrictRoutingModel):
    question: RoutingTaskText
    objective: RoutingTaskText
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )


class ComputationScalarSelection(StrictRoutingModel):
    name: ComputationInputName
    numeric_id: RoutingNumericId


class ComputationSeriesSelection(StrictRoutingModel):
    name: ComputationInputName
    numeric_ids: tuple[RoutingNumericId, ...] = Field(
        min_length=1,
        max_length=32,
    )


class ComputationPrecisionSelection(StrictRoutingModel):
    mode: Literal["decimal_places", "significant_figures"]
    digits_numeric_id: RoutingNumericId


class ComputationRoutingIntent(StrictRoutingModel):
    objective: RoutingTaskText
    scalar_inputs: tuple[ComputationScalarSelection, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    series_inputs: tuple[ComputationSeriesSelection, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    precision: ComputationPrecisionSelection | None = None
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_unique_inputs(self) -> Self:
        if not (self.scalar_inputs or self.series_inputs):
            raise ValueError("At least one computation input is required.")
        names = tuple(
            selection.name
            for selection in (*self.scalar_inputs, *self.series_inputs)
        )
        if len(set(names)) != len(names):
            raise ValueError("Computation input names must be unique.")
        operand_ids = tuple(
            selection.numeric_id for selection in self.scalar_inputs
        ) + tuple(
            numeric_id
            for selection in self.series_inputs
            for numeric_id in selection.numeric_ids
        )
        if len(set(operand_ids)) != len(operand_ids):
            raise ValueError("Computation numeric IDs must be unique.")
        if (
            self.precision is not None
            and self.precision.digits_numeric_id in operand_ids
        ):
            raise ValueError("Precision numeric ID cannot be an operand.")
        return self


class AgentColRoutingDirective(StrictRoutingModel):
    schema_version: Literal["2.0"] = "2.0"
    route: AgentColRoute
    clarifying_question: RoutingClarificationText | None = None
    source_intent: SourceRoutingIntent | None = None
    research_intent: ResearchRoutingIntent | None = None
    computation_intent: ComputationRoutingIntent | None = None

    @model_validator(mode="after")
    def require_matching_route_payload(self) -> Self:
        expected_presence = {
            AgentColRoute.DIRECT: (False, False, False, False),
            AgentColRoute.CLARIFY: (True, False, False, False),
            AgentColRoute.SOURCE: (False, True, False, False),
            AgentColRoute.RESEARCH: (False, False, True, False),
            AgentColRoute.COMPUTATION: (False, False, False, True),
        }
        actual_presence = (
            self.clarifying_question is not None,
            self.source_intent is not None,
            self.research_intent is not None,
            self.computation_intent is not None,
        )
        if actual_presence != expected_presence[self.route]:
            raise ValueError("Routing payload does not match its route.")
        return self


def validate_routing_directive_for_input(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> AgentColRoutingDirective:
    """Validate one v2 directive against its exact bounded routing input."""
    incompatible = "Routing directive is incompatible with its input."

    if directive.route is AgentColRoute.SOURCE:
        if ExpertCapability.SOURCE not in routing_input.available_capabilities:
            raise RoutingDirectiveInputError(incompatible)
        if directive.source_intent is None or not routing_input.candidate_urls:
            raise RoutingDirectiveInputError(incompatible)
        available_url_ids = {
            candidate.candidate_id for candidate in routing_input.candidate_urls
        }
        if not set(directive.source_intent.selected_url_ids) <= available_url_ids:
            raise RoutingDirectiveInputError(incompatible)

    if (
        directive.route is AgentColRoute.RESEARCH
        and ExpertCapability.RESEARCH not in routing_input.available_capabilities
    ):
        raise RoutingDirectiveInputError(incompatible)

    if directive.route is AgentColRoute.COMPUTATION:
        _validate_computation_directive(
            directive,
            routing_input,
            incompatible=incompatible,
        )

    return directive


def _validate_computation_directive(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
    *,
    incompatible: str,
) -> None:
    intent = directive.computation_intent
    if (
        ExpertCapability.COMPUTATION
        not in routing_input.available_capabilities
        or routing_input.numeric_projection_incomplete
        or intent is None
    ):
        raise RoutingDirectiveInputError(incompatible)

    candidates_by_id = {
        candidate.candidate_id: candidate
        for candidate in routing_input.numeric_candidates
    }
    candidate_order = {
        candidate.candidate_id: index
        for index, candidate in enumerate(routing_input.numeric_candidates)
    }
    selected_ids = tuple(
        selection.numeric_id for selection in intent.scalar_inputs
    ) + tuple(
        numeric_id
        for selection in intent.series_inputs
        for numeric_id in selection.numeric_ids
    )
    if intent.precision is not None:
        selected_ids += (intent.precision.digits_numeric_id,)
    if not set(selected_ids) <= set(candidates_by_id):
        raise RoutingDirectiveInputError(incompatible)

    try:
        validate_computation_task_text(intent.objective)
        for constraint in intent.constraints:
            validate_computation_task_text(constraint)
        if contains_numeric_like_text(intent.objective) or any(
            contains_numeric_like_text(value) for value in intent.constraints
        ):
            raise ValueError("Computation task text contains numeric data.")

        for series in intent.series_inputs:
            order = tuple(candidate_order[value] for value in series.numeric_ids)
            if order != tuple(sorted(order)):
                raise ValueError("Computation series is out of source order.")
            units = {
                (
                    candidates_by_id[value].notation,
                    candidates_by_id[value].unit_symbol,
                )
                for value in series.numeric_ids
            }
            if len(units) != 1:
                raise ValueError("Computation series units are incompatible.")

        if intent.precision is not None:
            precision_value = candidates_by_id[
                intent.precision.digits_numeric_id
            ].value
            if not precision_value.is_integer():
                raise ValueError("Computation precision must be an integer.")
            PrecisionRule(
                mode=intent.precision.mode,
                digits=int(precision_value),
            )
    except (TypeError, ValueError, ValidationError) as exc:
        raise RoutingDirectiveInputError(incompatible) from exc
