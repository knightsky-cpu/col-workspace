from collections.abc import Mapping
from typing import Literal, Self

from google.adk.tools import FunctionTool, ToolContext
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from expert_contracts import ExpertCapability, ExpertStatus
from expert_delegation import (
    ExpertDelegationDeniedError,
    ExpertDelegationDenialReason,
    ExpertDelegationRegistry,
)
from source_expert import (
    SOURCE_EXPERT_TIMEOUT_SECONDS,
    SourceExpertInput,
    SourceExpertResult,
)
from source_expert_service import (
    SourceExpertService,
    SourceExpertServiceError,
)


class SourceExpertToolResponseError(RuntimeError):
    """Raised when a Source tool response violates its contract."""


class _StrictSourceToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompletedSourceExpertToolResponse(_StrictSourceToolResponse):
    status: Literal["completed"]
    result: SourceExpertResult

    @model_validator(mode="after")
    def require_completed_result(self) -> Self:
        if self.result.status is not ExpertStatus.COMPLETED:
            raise ValueError("Source result is not completed.")
        return self


class FailedSourceExpertToolResponse(_StrictSourceToolResponse):
    status: Literal[
        ExpertStatus.REJECTED_INPUT,
        ExpertStatus.UNAVAILABLE,
        ExpertStatus.TIMED_OUT,
        ExpertStatus.INVALID_OUTPUT,
    ]
    message: Literal["Source analysis could not be completed."]


SourceExpertToolResponse = (
    CompletedSourceExpertToolResponse | FailedSourceExpertToolResponse
)


def parse_source_expert_tool_response(
    value: object,
) -> SourceExpertToolResponse:
    """Validate one Source tool response envelope."""
    try:
        if not isinstance(value, Mapping):
            raise ValueError("Response must be a mapping.")
        if value.get("status") == "completed":
            return CompletedSourceExpertToolResponse.model_validate(value)
        return FailedSourceExpertToolResponse.model_validate(value)
    except (TypeError, ValueError, ValidationError) as exc:
        raise SourceExpertToolResponseError(
            "Source Expert tool response is invalid."
        ) from exc


def _failed_response(status: ExpertStatus) -> dict[str, object]:
    return {
        "status": status.value,
        "message": "Source analysis could not be completed.",
    }


def _delegation_failure_status(
    error: ExpertDelegationDeniedError,
) -> ExpertStatus:
    if error.reason is (
        ExpertDelegationDenialReason.INSUFFICIENT_TIME_REMAINING
    ):
        return ExpertStatus.TIMED_OUT
    if error.reason is ExpertDelegationDenialReason.TURN_NOT_REGISTERED:
        return ExpertStatus.UNAVAILABLE
    return ExpertStatus.REJECTED_INPUT


def create_source_expert_tool(
    *,
    source_service: SourceExpertService,
    delegation_registry: ExpertDelegationRegistry,
) -> FunctionTool:
    """Create Agent_Col's bounded public-URL analysis tool."""

    async def analyze_source(
        objective: str,
        urls: list[str],
        constraints: list[str],
        tool_context: ToolContext,
    ) -> dict[str, object]:
        """Analyze or compare one to three supplied public URLs."""
        state = getattr(tool_context, "state", None)
        state_get = getattr(state, "get", None)
        token = (
            state_get("expert_delegation_token")
            if callable(state_get)
            else None
        )
        if not isinstance(token, str):
            return _failed_response(ExpertStatus.UNAVAILABLE)
        try:
            await delegation_registry.claim(
                token,
                ExpertCapability.SOURCE,
                depth=1,
                minimum_remaining_seconds=SOURCE_EXPERT_TIMEOUT_SECONDS,
            )
        except ExpertDelegationDeniedError as exc:
            return _failed_response(_delegation_failure_status(exc))
        try:
            request = SourceExpertInput(
                objective=objective,
                urls=tuple(urls),
                constraints=tuple(constraints),
            )
        except ValidationError:
            return _failed_response(ExpertStatus.REJECTED_INPUT)
        try:
            result = await source_service.analyze(request)
        except SourceExpertServiceError as exc:
            return _failed_response(exc.status)
        if result.status is not ExpertStatus.COMPLETED:
            return _failed_response(ExpertStatus.INVALID_OUTPUT)
        return {
            "status": "completed",
            "result": result.model_dump(mode="json"),
        }

    return FunctionTool(analyze_source)
