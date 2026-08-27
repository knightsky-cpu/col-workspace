from enum import StrEnum
from typing import Annotated, Generic, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


ExpertSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_500),
]
ExpertLimitation = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ExpertInvalidOutputReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]


class ExpertCapability(StrEnum):
    """Approved bounded expert capabilities."""

    RESEARCH = "research"
    SOURCE = "source"
    COMPUTATION = "computation"
    REQUIREMENTS_VERIFICATION = "requirements_verification"


class ExpertStatus(StrEnum):
    """Normalized outcomes allowed across expert boundaries."""

    COMPLETED = "completed"
    REJECTED_INPUT = "rejected_input"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    INVALID_OUTPUT = "invalid_output"


PayloadT = TypeVar("PayloadT")
EvidenceT = TypeVar("EvidenceT")


class ExpertResult(BaseModel, Generic[PayloadT, EvidenceT]):
    """Internal normalized result returned by an expert adapter."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    capability: ExpertCapability
    status: ExpertStatus
    summary: ExpertSummary | None = None
    limitations: tuple[ExpertLimitation, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    invalid_output_reason: ExpertInvalidOutputReason | None = None
    payload: PayloadT | None = None
    evidence: EvidenceT | None = None

    @model_validator(mode="after")
    def validate_completed_result(self) -> Self:
        if self.status is ExpertStatus.COMPLETED and (
            self.summary is None
            or self.payload is None
            or self.evidence is None
        ):
            raise ValueError(
                "Completed expert results require summary, payload, "
                "and evidence."
            )
        if self.status is not ExpertStatus.COMPLETED and (
            self.summary is not None
            or self.limitations
            or self.payload is not None
            or self.evidence is not None
        ):
            raise ValueError(
                "Noncompleted expert results cannot carry content."
            )
        if (
            self.invalid_output_reason is not None
            and self.status is not ExpertStatus.INVALID_OUTPUT
        ):
            raise ValueError(
                "Only invalid-output expert results can carry an "
                "invalid-output reason."
            )
        return self
