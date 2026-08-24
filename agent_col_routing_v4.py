"""Parallel Agent_Col routing v4 contracts with artifact selection."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_col_routing import (
    RoutingClarificationText,
    RoutingTaskText,
)
from agent_col_numeric_projection import contains_numeric_like_text
from agent_col_routing_v2 import (
    ComputationRoutingIntent,
    ResearchRoutingIntent,
    SourceRoutingIntent,
)
from agent_col_routing_v3 import (
    AgentColRoutingDirective as AgentColRoutingDirectiveV3,
    AgentColRoutingInput as AgentColRoutingInputV3,
    RequirementsVerificationRoutingIntent,
    RoutingDirectiveInputError as RoutingDirectiveInputErrorV3,
    StrictRoutingModel,
    validate_routing_directive_for_input as validate_v3_directive_for_input,
)


class AgentColRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    SOURCE = "source"
    RESEARCH = "research"
    COMPUTATION = "computation"
    REQUIREMENTS_VERIFICATION = "requirements_verification"
    ARTIFACT = "artifact"


class RoutingDirectiveInputReason(StrEnum):
    """Allowlisted, content-free v4 routing incompatibility classes."""

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
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    STRUCTURED_DECISION_PRESENT = "structured_decision_present"


class RoutingDirectiveInputError(RuntimeError):
    """Raised when a valid v4 directive cannot execute against its input."""

    def __init__(
        self,
        reason: RoutingDirectiveInputReason | str = (
            RoutingDirectiveInputReason.UNKNOWN_INPUT_MISMATCH
        ),
    ) -> None:
        try:
            self.reason = RoutingDirectiveInputReason(reason)
        except ValueError:
            self.reason = RoutingDirectiveInputReason.UNKNOWN_INPUT_MISMATCH
        super().__init__("Routing directive is incompatible with its input.")


class AgentColRoutingInput(AgentColRoutingInputV3):
    recent_user_messages: tuple[RoutingTaskText, ...] = Field(
        default_factory=tuple,
        max_length=6,
    )
    artifact_creation_available: bool = False
    structured_decision_present: bool = False


class ArtifactRoutingIntent(StrictRoutingModel):
    operation: Literal["create_blueprint"]
    objective: RoutingTaskText


class AgentColRoutingDirective(StrictRoutingModel):
    schema_version: Literal["4.0"] = "4.0"
    route: AgentColRoute
    clarifying_question: RoutingClarificationText | None = None
    source_intent: SourceRoutingIntent | None = None
    research_intent: ResearchRoutingIntent | None = None
    computation_intent: ComputationRoutingIntent | None = None
    requirements_verification_intent: (
        RequirementsVerificationRoutingIntent | None
    ) = None
    artifact_intent: ArtifactRoutingIntent | None = None

    @model_validator(mode="after")
    def require_matching_route_payload(self) -> Self:
        expected_presence = {
            AgentColRoute.DIRECT: (False, False, False, False, False, False),
            AgentColRoute.CLARIFY: (True, False, False, False, False, False),
            AgentColRoute.SOURCE: (False, True, False, False, False, False),
            AgentColRoute.RESEARCH: (False, False, True, False, False, False),
            AgentColRoute.COMPUTATION: (
                False,
                False,
                False,
                True,
                False,
                False,
            ),
            AgentColRoute.REQUIREMENTS_VERIFICATION: (
                False,
                False,
                False,
                False,
                True,
                False,
            ),
            AgentColRoute.ARTIFACT: (False, False, False, False, False, True),
        }
        actual_presence = (
            self.clarifying_question is not None,
            self.source_intent is not None,
            self.research_intent is not None,
            self.computation_intent is not None,
            self.requirements_verification_intent is not None,
            self.artifact_intent is not None,
        )
        if actual_presence != expected_presence[self.route]:
            raise ValueError("Routing payload does not match its route.")
        return self


def validate_routing_directive_for_input(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> AgentColRoutingDirective:
    """Validate one v4 directive against its exact bounded routing input."""
    if directive.route is AgentColRoute.ARTIFACT:
        if not routing_input.artifact_creation_available:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.ARTIFACT_UNAVAILABLE
            )
        if routing_input.structured_decision_present:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.STRUCTURED_DECISION_PRESENT
            )
        if directive.artifact_intent is None:
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.MISSING_REQUIRED_INPUT
            )
        if contains_numeric_like_text(directive.artifact_intent.objective):
            raise RoutingDirectiveInputError(
                RoutingDirectiveInputReason.UNSAFE_TASK_TEXT
            )
        return directive

    v3_directive = AgentColRoutingDirectiveV3.model_validate(
        directive.model_dump(exclude={"artifact_intent", "schema_version"})
        | {"schema_version": "3.0"}
    )
    v3_input = AgentColRoutingInputV3.model_validate(
        routing_input.model_dump(
            exclude={
                "artifact_creation_available",
                "structured_decision_present",
                "recent_user_messages",
            }
        )
    )
    try:
        validate_v3_directive_for_input(v3_directive, v3_input)
    except RoutingDirectiveInputErrorV3 as exc:
        raise RoutingDirectiveInputError(exc.reason.value) from exc
    return directive
