"""Parallel Agent_Col routing v3 contracts for compatibility testing."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from agent_col_numeric_projection import (
    RoutingNumericCandidate,
    contains_numeric_like_text,
)
from agent_col_routing import (
    RoutingClarificationText,
    RoutingConstraintText,
    RoutingTaskText,
    RoutingUrlCandidate,
)
from agent_col_routing_v2 import (
    ComputationPrecisionSelection,
    ComputationRoutingIntent,
    ComputationScalarSelection,
    ComputationSeriesSelection,
    ResearchRoutingIntent,
    SourceRoutingIntent,
)
from agent_col_text_projection import (
    RoutingTextBlockCandidate,
    RoutingTextBlockId,
    RoutingTextBlockKind,
)
from computational_expert import PrecisionRule, validate_computation_task_text
from expert_contracts import ExpertCapability


RoutingV3MessageText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10_000),
]


class AgentColRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    SOURCE = "source"
    RESEARCH = "research"
    COMPUTATION = "computation"
    REQUIREMENTS_VERIFICATION = "requirements_verification"


class RoutingDirectiveInputReason(StrEnum):
    """Allowlisted, content-free routing/input incompatibility classes."""

    UNKNOWN_INPUT_MISMATCH = "unknown_input_mismatch"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    MISSING_REQUIRED_INPUT = "missing_required_input"
    INCOMPLETE_NUMERIC_PROJECTION = "incomplete_numeric_projection"
    UNKNOWN_NUMERIC_CANDIDATE = "unknown_numeric_candidate"
    NUMERIC_TASK_TEXT = "numeric_task_text"
    UNSAFE_TASK_TEXT = "unsafe_task_text"
    SERIES_ORDER_MISMATCH = "series_order_mismatch"
    SERIES_UNIT_MISMATCH = "series_unit_mismatch"
    INVALID_PRECISION = "invalid_precision"


class RoutingDirectiveInputError(RuntimeError):
    """Raised when a valid v3 directive cannot execute against its input."""

    def __init__(
        self,
        reason: RoutingDirectiveInputReason | str = (
            RoutingDirectiveInputReason.UNKNOWN_INPUT_MISMATCH
        ),
    ) -> None:
        self.reason = (
            reason
            if isinstance(reason, RoutingDirectiveInputReason)
            else RoutingDirectiveInputReason.UNKNOWN_INPUT_MISMATCH
        )
        super().__init__("Routing directive is incompatible with its input.")


class StrictRoutingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class AgentColRoutingInput(StrictRoutingModel):
    current_message: RoutingV3MessageText
    candidate_urls: tuple[RoutingUrlCandidate, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    numeric_candidates: tuple[RoutingNumericCandidate, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    numeric_projection_incomplete: bool = False
    text_block_candidates: tuple[RoutingTextBlockCandidate, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    text_projection_incomplete: bool = False
    available_capabilities: tuple[ExpertCapability, ...] = Field(
        default_factory=tuple,
        max_length=4,
    )

    @field_validator("current_message")
    @classmethod
    def reject_whitespace_only_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Routing message cannot be whitespace only.")
        return value

    @model_validator(mode="after")
    def require_valid_bounded_context(self) -> Self:
        allowed_capabilities = {
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
            ExpertCapability.COMPUTATION,
            ExpertCapability.REQUIREMENTS_VERIFICATION,
        }
        if not set(self.available_capabilities) <= allowed_capabilities:
            raise ValueError("Routing capability is not available.")
        if len(set(self.available_capabilities)) != len(
            self.available_capabilities
        ):
            raise ValueError("Routing capabilities must be unique.")

        url_ids = tuple(
            candidate.candidate_id for candidate in self.candidate_urls
        )
        urls = tuple(str(candidate.url) for candidate in self.candidate_urls)
        if len(set(url_ids)) != len(url_ids):
            raise ValueError("Routing candidate IDs must be unique.")
        if len(set(urls)) != len(urls):
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

        previous_end = -1
        for index, candidate in enumerate(
            self.text_block_candidates,
            start=1,
        ):
            if candidate.candidate_id != f"block-{index}":
                raise ValueError("Text block candidate IDs must be sequential.")
            if (
                self.current_message[
                    candidate.start_index:candidate.end_index
                ]
                != candidate.text
            ):
                raise ValueError("Text block candidate span does not match input.")
            if candidate.start_index < previous_end:
                raise ValueError("Text block candidate spans must not overlap.")
            previous_end = candidate.end_index
        return self


class RequirementsVerificationRoutingIntent(StrictRoutingModel):
    objective: RoutingTaskText
    requirement_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        min_length=1,
        max_length=50,
    )
    subject_block_ids: tuple[RoutingTextBlockId, ...] = Field(
        min_length=1,
        max_length=32,
    )
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_unique_disjoint_selections(self) -> Self:
        requirement_ids = self.requirement_block_ids
        subject_ids = self.subject_block_ids
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("Requirement block IDs must be unique.")
        if len(set(subject_ids)) != len(subject_ids):
            raise ValueError("Subject block IDs must be unique.")
        if set(requirement_ids) & set(subject_ids):
            raise ValueError("Requirement and subject blocks must be disjoint.")
        return self


class AgentColRoutingDirective(StrictRoutingModel):
    schema_version: Literal["3.0"] = "3.0"
    route: AgentColRoute
    clarifying_question: RoutingClarificationText | None = None
    source_intent: SourceRoutingIntent | None = None
    research_intent: ResearchRoutingIntent | None = None
    computation_intent: ComputationRoutingIntent | None = None
    requirements_verification_intent: (
        RequirementsVerificationRoutingIntent | None
    ) = None

    @model_validator(mode="after")
    def require_matching_route_payload(self) -> Self:
        expected_presence = {
            AgentColRoute.DIRECT: (False, False, False, False, False),
            AgentColRoute.CLARIFY: (True, False, False, False, False),
            AgentColRoute.SOURCE: (False, True, False, False, False),
            AgentColRoute.RESEARCH: (False, False, True, False, False),
            AgentColRoute.COMPUTATION: (False, False, False, True, False),
            AgentColRoute.REQUIREMENTS_VERIFICATION: (
                False,
                False,
                False,
                False,
                True,
            ),
        }
        actual_presence = (
            self.clarifying_question is not None,
            self.source_intent is not None,
            self.research_intent is not None,
            self.computation_intent is not None,
            self.requirements_verification_intent is not None,
        )
        if actual_presence != expected_presence[self.route]:
            raise ValueError("Routing payload does not match its route.")
        return self


def validate_routing_directive_for_input(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> AgentColRoutingDirective:
    """Validate one v3 directive against its exact bounded routing input."""
    if directive.route is AgentColRoute.SOURCE:
        if ExpertCapability.SOURCE not in routing_input.available_capabilities:
            raise RoutingDirectiveInputError()
        if directive.source_intent is None or not routing_input.candidate_urls:
            raise RoutingDirectiveInputError()
        available_url_ids = {
            candidate.candidate_id for candidate in routing_input.candidate_urls
        }
        if not set(directive.source_intent.selected_url_ids) <= available_url_ids:
            raise RoutingDirectiveInputError()

    if (
        directive.route is AgentColRoute.RESEARCH
        and ExpertCapability.RESEARCH not in routing_input.available_capabilities
    ):
        raise RoutingDirectiveInputError()

    if directive.route is AgentColRoute.COMPUTATION:
        _validate_computation_directive(directive, routing_input)

    if directive.route is AgentColRoute.REQUIREMENTS_VERIFICATION:
        _validate_requirements_directive(directive, routing_input)
    return directive


def _validate_computation_directive(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> None:
    intent = directive.computation_intent
    if ExpertCapability.COMPUTATION not in routing_input.available_capabilities:
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.CAPABILITY_UNAVAILABLE
        )
    if routing_input.numeric_projection_incomplete:
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.INCOMPLETE_NUMERIC_PROJECTION
        )
    if intent is None:
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.MISSING_REQUIRED_INPUT
        )

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
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.UNKNOWN_NUMERIC_CANDIDATE
        )

    try:
        validate_computation_task_text(intent.objective)
        for constraint in intent.constraints:
            validate_computation_task_text(constraint)
    except ValueError as exc:
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.UNSAFE_TASK_TEXT
        ) from exc

    if contains_numeric_like_text(intent.objective) or any(
        contains_numeric_like_text(value) for value in intent.constraints
    ):
        raise RoutingDirectiveInputError(
            RoutingDirectiveInputReason.NUMERIC_TASK_TEXT
        )

    for series in intent.series_inputs:
        try:
            order = tuple(candidate_order[value] for value in series.numeric_ids)
        except KeyError as exc:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.UNKNOWN_NUMERIC_CANDIDATE
            ) from exc
        if order != tuple(sorted(order)):
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.SERIES_ORDER_MISMATCH
            )
        units = {
            (
                candidates_by_id[value].notation,
                candidates_by_id[value].unit_symbol,
            )
            for value in series.numeric_ids
        }
        if len(units) != 1:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.SERIES_UNIT_MISMATCH
            )

    if intent.precision is not None:
        precision_value = candidates_by_id[
            intent.precision.digits_numeric_id
        ].value
        if not precision_value.is_integer():
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.INVALID_PRECISION
            )
        try:
            PrecisionRule(
                mode=intent.precision.mode,
                digits=int(precision_value),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.INVALID_PRECISION
            ) from exc


def _validate_requirements_directive(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> None:
    intent = directive.requirements_verification_intent
    if (
        ExpertCapability.REQUIREMENTS_VERIFICATION
        not in routing_input.available_capabilities
        or routing_input.text_projection_incomplete
        or intent is None
    ):
        raise RoutingDirectiveInputError()

    candidates_by_id = {
        candidate.candidate_id: candidate
        for candidate in routing_input.text_block_candidates
    }
    candidate_order = {
        candidate.candidate_id: index
        for index, candidate in enumerate(routing_input.text_block_candidates)
    }
    selected_ids = (
        *intent.requirement_block_ids,
        *intent.subject_block_ids,
    )
    if not set(selected_ids) <= set(candidates_by_id):
        raise RoutingDirectiveInputError()

    try:
        requirement_candidates = tuple(
            candidates_by_id[value]
            for value in intent.requirement_block_ids
        )
        subject_candidates = tuple(
            candidates_by_id[value] for value in intent.subject_block_ids
        )
        if any(
            candidate.structural_kind
            not in {
                RoutingTextBlockKind.LIST_ITEM,
                RoutingTextBlockKind.PARAGRAPH,
            }
            for candidate in requirement_candidates
        ):
            raise ValueError("Requirement block kind is not allowed.")
        if any(
            candidate.structural_kind
            not in {
                RoutingTextBlockKind.LIST_ITEM,
                RoutingTextBlockKind.PARAGRAPH,
                RoutingTextBlockKind.FENCED_BLOCK,
            }
            for candidate in subject_candidates
        ):
            raise ValueError("Subject block kind is not allowed.")

        for selected in (
            intent.requirement_block_ids,
            intent.subject_block_ids,
        ):
            order = tuple(candidate_order[value] for value in selected)
            if order != tuple(sorted(order)):
                raise ValueError("Text block selection is out of source order.")

        if any(len(candidate.text) > 1_000 for candidate in requirement_candidates):
            raise ValueError("Requirement block is too long.")
        if any(len(candidate.text) > 8_000 for candidate in subject_candidates):
            raise ValueError("Subject block is too long.")

        requirement_characters = sum(
            len(candidate.text) for candidate in requirement_candidates
        )
        subject_characters = sum(
            len(candidate.text) for candidate in subject_candidates
        )
        if (
            requirement_characters > 6_000
            or subject_characters > 8_000
            or requirement_characters + subject_characters > 9_000
        ):
            raise ValueError("Selected text exceeds routing bounds.")
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingDirectiveInputError() from exc
